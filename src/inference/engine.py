"""
PatchCoreEngine — bản triển khai rút gọn của thuật toán PatchCore
(Roth et al., "Towards Total Recall in Industrial Anomaly Detection", 2022).

Ý tưởng cốt lõi:
1. Dùng backbone CNN đã pretrain trên ImageNet để trích đặc trưng TRUNG GIAN
   (không phải lớp cuối) — giữ được thông tin vị trí không gian của từng vùng ảnh.
2. Lưu toàn bộ đặc trưng từ ảnh "tốt" vào 1 ngân hàng (memory bank).
3. Với ảnh mới: so từng vùng nhỏ với ngân hàng bằng nearest-neighbor,
   lấy vùng lệch nhiều nhất làm điểm bất thường của cả ảnh.

Cần cài: torch, torchvision (xem requirements.txt ở thư mục gốc).
"""
from __future__ import annotations
import random
from pathlib import Path

import torch
import torch.nn.functional as F
from PIL import Image
from torchvision import models, transforms


class PatchCoreEngine:
    def __init__(self, backbone: str = "wide_resnet50_2", device: str | None = None,
                 pretrained: bool = True, image_size: int = 224):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.image_size = image_size
        self.backbone_name = backbone

        weights = "DEFAULT" if pretrained else None
        net = getattr(models, backbone)(weights=weights)
        net.eval().to(self.device)
        for p in net.parameters():
            p.requires_grad_(False)
        self.net = net

        # layer2 + layer3 là lựa chọn chuẩn trong PatchCore gốc: đủ sâu để
        # có ngữ nghĩa, đủ nông để còn giữ chi tiết không gian cho việc khoanh vùng lỗi.
        self._features: dict[str, torch.Tensor] = {}
        net.layer2.register_forward_hook(self._hook("layer2"))
        net.layer3.register_forward_hook(self._hook("layer3"))

        self.preprocess = transforms.Compose([
            transforms.Resize((image_size, image_size)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])

        self.memory_bank: torch.Tensor | None = None  # [N, C]

    def _hook(self, name: str):
        def fn(_module, _input, output):
            self._features[name] = output
        return fn

    @torch.no_grad()
    def extract_patch_embeddings(self, image: Image.Image) -> torch.Tensor:
        """Trả về [num_patches, C]: mỗi hàng là đặc trưng của 1 vùng nhỏ trên ảnh."""
        x = self.preprocess(image.convert("RGB")).unsqueeze(0).to(self.device)
        self._features.clear()
        self.net(x)
        f2, f3 = self._features["layer2"], self._features["layer3"]
        f3 = F.interpolate(f3, size=f2.shape[-2:], mode="bilinear", align_corners=False)
        fmap = torch.cat([f2, f3], dim=1)          # [1, C, H, W]
        _, c, h, w = fmap.shape
        return fmap.permute(0, 2, 3, 1).reshape(h * w, c).cpu()

    def build_memory_bank(self, image_paths: list[Path], coreset_size: int = 4000,
                           seed: int = 0) -> None:
        """Trích đặc trưng từ toàn bộ ảnh tốt, nén ngân hàng bằng lấy mẫu ngẫu
        nhiên nếu quá lớn (coreset subsampling đơn giản hóa) để so khớp vẫn nhanh."""
        chunks = [self.extract_patch_embeddings(Image.open(p)) for p in image_paths]
        bank = torch.cat(chunks, dim=0)
        if bank.shape[0] > coreset_size:
            rng = random.Random(seed)
            idx = rng.sample(range(bank.shape[0]), coreset_size)
            bank = bank[idx]
        self.memory_bank = bank

    @torch.no_grad()
    def score(self, image: Image.Image) -> dict:
        """Điểm bất thường = khoảng cách lớn nhất trong số các khoảng cách
        nearest-neighbor của từng vùng ảnh tới ngân hàng đặc trưng."""
        if self.memory_bank is None:
            raise RuntimeError("Chưa có ngân hàng đặc trưng — gọi build_memory_bank() hoặc load() trước.")
        patches = self.extract_patch_embeddings(image)          # [P, C]
        dists = torch.cdist(patches, self.memory_bank)           # [P, N]
        nn_dist, _ = dists.min(dim=1)                             # [P]
        side = int(round(nn_dist.shape[0] ** 0.5))
        heatmap = nn_dist.reshape(side, side).tolist() if side * side == nn_dist.shape[0] else None
        return {"score": float(nn_dist.max()), "heatmap": heatmap, "grid": side}

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save({
            "backbone": self.backbone_name,
            "image_size": self.image_size,
            "memory_bank": self.memory_bank,
        }, path)

    @classmethod
    def load(cls, path: Path, device: str | None = None) -> "PatchCoreEngine":
        ckpt = torch.load(path, map_location="cpu")
        # Backbone phải dùng pretrained weights chuẩn (giống lúc train) để
        # đặc trưng trích ra khớp với ngân hàng đã lưu.
        eng = cls(backbone=ckpt["backbone"], device=device, pretrained=True,
                   image_size=ckpt["image_size"])
        eng.memory_bank = ckpt["memory_bank"]
        return eng
