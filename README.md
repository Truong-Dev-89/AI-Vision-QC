# AI Vision QC — Multi-Product Project Scaffold

## Web UI with live camera

```bash
uvicorn api.app:app --reload --port 8000
```

Open your browser at **http://127.0.0.1:8000/ui/** — the UI lets you:
- Turn on the webcam/camera and see a live feed (language switcher: VI / 中文 / EN)
- Pick a product, enter/scan a serial number, click "Capture & Inspect"
- Immediately see the annotated image (red-boxed defect region, if any) and the pass/suspect/reject result
- Switch to the "Return scan" tab to cross-check by serial number (see below)
- Confirm Good/Defect right in the UI to keep the AI learning

## Cross-checking two scans: outbound shipment vs. customer return (the main self-learning loop)

```
Outbound: POST /inspect/<product_id>  (with serial=<SN>)  -> logs the result under that SN
Return:   POST /return-scan/<product_id>  (with serial=<SN>)  -> automatically looks up the old log
```

- If **outbound: pass** but **return: the AI detects a defect** → clear evidence
  of a real missed defect. The system **automatically** adds it to `confirmed_ng/`,
  no human confirmation needed — this is the most valuable data for reducing
  defective units reaching customers.
- If **the return scan still looks normal** → the system does **not** auto-label,
  since it could be a functional defect (invisible to the camera) or shipping
  damage. A human needs to confirm manually via `POST /feedback` before it's
  added to the training data.

## Deploying multiple camera stations against one server

When one machine runs the API for multiple other stations on the factory
floor (not just running alone on `127.0.0.1` anymore), there are 2 MANDATORY steps:

### 1. Get the API key

When you run `uvicorn`, the terminal prints a line like:
```
API KEY for this station: xxxxxxxxxxxxxxxxxxxxxxxxxxxx
```
Each station opens `/ui/`, pastes this exact key into the "API key" field,
clicks "Save" — only needs to be done once per browser. The key is stored in
the `.api_key` file at the project root — **never push this file to git**
(already excluded via `.gitignore`).

### 2. Enable HTTPS (required for the camera to work over the network)

Browsers ONLY allow a web page to use the camera when accessed via
`localhost` OR over HTTPS — no exceptions. If other stations access it by IP
address over plain HTTP, the camera will **never turn on**, no matter how
correct the code is.

Generate a self-signed certificate (one-time, requires OpenSSL — bundled
with Git for Windows):
```powershell
openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes -subj "/CN=vision-qc-local"
```

Run the server with HTTPS, allowing other machines on the network to connect (`--host 0.0.0.0`):
```powershell
uvicorn api.app:app --host 0.0.0.0 --port 8000 --ssl-keyfile key.pem --ssl-certfile cert.pem
```

Other stations access it via: `https://<server-ip-address>:8000/ui/`
(e.g. `https://192.168.1.50:8000/ui/`). The browser will warn "Not secure"
because of the self-signed certificate — this is expected on an internal
network; click "Advanced" → "Proceed" to continue, only needed once per station.

**Do not expose this port to the internet** (no port-forwarding on the
router) — the system is designed for an internal factory network only.

## How to actually run it (real code, not just an empty scaffold)

```bash
# 1. Install dependencies (needs internet to download PyTorch + pretrained weights)
pip install -r requirements.txt

# 2. Put "good" images in the right folder (minimum 20-30 images)
#    data/raw/<product_id>/good/image1.jpg, image2.jpg, ...

# 3. Train — really means building a "memory bank" from the good images
python training/train.py --product <product_id>
#    -> prints the model path + a suggested threshold

# 4. Copy configs/products/_template.yaml -> configs/products/<product_id>.yaml
#    fill in model.path and decision.threshold from step 3's output

# 5. Run the API to inspect images over HTTP
uvicorn api.app:app --reload --port 8000
#    POST /inspect/<product_id>            (with an image file) -> pass/suspect/reject result
#    POST /feedback/{product_id}/{image_id}?is_good=true|false  -> records feedback for self-learning
```

## How the "self-learning" loop works
Every image flagged `suspect`/`reject` is automatically saved to
`data/raw/<product_id>/suspect/`. When you call `/feedback` to confirm
right/wrong, the image is moved into `good/` (if the AI was wrong) or
`confirmed_ng/` (if it really was a defect). Once enough new images
accumulate (`min_new_samples` in the config), re-run `training/train.py` —
the model learns from those exact images, following the safe version-control
procedure in `docs/retrain_policy.md`.

---

## Core principle (folder design)
The system is designed in 2 separate layers, so adding a new product does
NOT require touching the core source code:

1. **Platform layer (`src/`)**: image processing, running the model, making
   decisions, PLC/MES integration. Shared by every product, rarely changes.
2. **Config layer (`configs/products/`)**: each product is its own YAML file
   pointing to its own model, data, and threshold.

Adding a new product: add a folder under `data/raw/`, train a model, add a
YAML file under `configs/products/` — don't touch `src/`.

## Folder structure

```
ai_vision_qc/
├── configs/products/     # 1 YAML file = 1 product type
├── data/
│   ├── raw/<product_id>/{good,suspect,confirmed_ng}/
│   ├── processed/        # preprocessed images, ready for training
│   └── logs/             # shipment_log.csv, returns_log.csv
├── models/<product_id>/  # trained weights, versioned
├── src/
│   ├── capture/          # camera interface, capture trigger
│   ├── preprocessing/    # ROI cropping, alignment, normalization
│   ├── inference/        # load model, compute anomaly score
│   ├── decision/         # pass/suspect/reject logic based on threshold
│   ├── feedback/         # self-learning loop: labeling, retrain triggers
│   ├── integration/      # PLC/MES connections
│   └── utils/            # shared helper functions
├── training/             # training script, model evaluation
├── api/                  # REST API for real-time inference
├── dashboard/            # defect-rate monitoring UI
├── tests/                # automated tests
├── deployment/
│   ├── docker/           # server deployment packaging
│   └── edge/             # config for Jetson/edge devices
└── docs/                 # operating docs, runbooks
```

## Naming conventions (keep consistent across the whole project)
- `product_id`: lowercase, no accents, underscores. Example: `board_a`, `plastic_wrap_b`
- Images: `<batch_code>_<serial>.jpg`, e.g. `LO20260924_SP00015.jpg`
- Models: `models/<product_id>/v<version>/model.pt`, e.g. `models/board_a/v3/model.pt`

## Workflow for adding a new product
1. Create `data/raw/<product_id>/good/` and drop good images into it
2. Run `training/train.py --product <product_id>` to train
3. Copy `configs/products/_template.yaml` → `configs/products/<product_id>.yaml`, fill in the values
4. The core system automatically recognizes the new product from its config file — no need to redeploy `src/`

## Self-learning feedback loop
`src/feedback/` is responsible for: any image flagged "suspect" or whose
result was corrected by an operator is automatically saved into
`data/raw/<product_id>/suspect/`. Periodically (weekly/monthly), re-run
`training/train.py` to update the model — see `docs/retrain_policy.md` for
the safe version-control procedure.
