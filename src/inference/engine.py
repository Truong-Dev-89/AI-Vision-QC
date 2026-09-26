"""
PatchCoreEngine — a simplified implementation of the PatchCore algorithm
(Roth et al., "Towards Total Recall in Industrial Anomaly Detection", 2022).

Core idea:
1. Use an ImageNet-pretrained CNN backbone to extract INTERMEDIATE features
   (not the final layer) — this keeps the spatial position information for
   each region of the image.
2. Store the features from every "good" image in a memory bank.
3. For a new image: compare each small region against the memory bank via
   nearest-neighbor, and take the worst-matching region as the image's
   anomaly score.

Requires: torch, torchvision (see requirements.txt at the project root).
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

        # layer2 + layer3 is the standard choice in the original PatchCore
        # paper: deep enough to carry semantic meaning, shallow enough to
        # still preserve spatial detail for localizing defects.
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
        """Returns [num_patches, C]: each row is the feature vector of one
        small region of the image."""
        x = self.preprocess(image.convert("RGB")).unsqueeze(0).to(self.device)
        self._features.clear()
        self.net(x)
        f2, f3 = self._features["layer2"], self._features["layer3"]
        f3 = F.interpolate(f3, size=f2.shape[-2:], mode="bilinear", align_corners=False)
        fmap = torch.cat([f2, f3], dim=1)          # [1, C, H, W]
        _, c, h, w = fmap.shape
        return fmap.permute(0, 2, 3, 1).reshape(h * w, c).cpu()

    def build_memory_bank(self, image_paths: list[Path], coreset_size: int = 2000,
                           candidate_pool: int = 8000, seed: int = 0) -> None:
        """Build the memory bank using GREEDY CORESET SUBSAMPLING — the same
        technique used in the original PatchCore paper, instead of plain
        random sampling.

        Greedy coreset repeatedly picks the point that is FARTHEST from the
        points already chosen (farthest-point sampling), so a small memory
        bank still covers the whole feature space evenly instead of being
        biased toward regions with many similar-looking images.

        Because comparing distances across tens of thousands of patches is
        slow, we first randomly subsample down to `candidate_pool`
        candidates, then run greedy coreset on that pool down to the final
        `coreset_size`.
        """
        chunks = [self.extract_patch_embeddings(Image.open(p)) for p in image_paths]
        bank = torch.cat(chunks, dim=0)

        rng = random.Random(seed)
        if bank.shape[0] > candidate_pool:
            idx = rng.sample(range(bank.shape[0]), candidate_pool)
            bank = bank[idx]

        self.memory_bank = self._greedy_coreset(bank, coreset_size, seed)

    @staticmethod
    def _greedy_coreset(bank: torch.Tensor, m: int, seed: int = 0) -> torch.Tensor:
        n = bank.shape[0]
        if n <= m:
            return bank
        first = random.Random(seed).randrange(n)
        selected = [first]
        min_dists = torch.cdist(bank, bank[[first]]).squeeze(1)
        for _ in range(m - 1):
            next_idx = int(torch.argmax(min_dists))
            selected.append(next_idx)
            new_dists = torch.cdist(bank, bank[[next_idx]]).squeeze(1)
            min_dists = torch.minimum(min_dists, new_dists)
        return bank[selected]

    @torch.no_grad()
    def score(self, image: Image.Image) -> dict:
        """Anomaly score = the largest nearest-neighbor distance among all
        regions of the image against the memory bank (built with greedy
        coreset in build_memory_bank, not random sampling)."""
        if self.memory_bank is None:
            raise RuntimeError("No memory bank yet — call build_memory_bank() or load() first.")
        patches = self.extract_patch_embeddings(image)            # [P, C]
        dists = torch.cdist(patches, self.memory_bank)             # [P, N]
        nn_dist, _ = dists.min(dim=1)                               # [P]
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
        # The backbone must use the same standard pretrained weights as during
        # training so extracted features match the saved memory bank.
        eng = cls(backbone=ckpt["backbone"], device=device, pretrained=True,
                   image_size=ckpt["image_size"])
        eng.memory_bank = ckpt["memory_bank"]
        return eng
