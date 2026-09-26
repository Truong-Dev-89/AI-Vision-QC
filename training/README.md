# training/
train.py: trains the model for one product_id from images in
data/raw/<product_id>/good/
evaluate.py: compares a newly trained model against the one currently in
production on confirmed_ng/ + good/ images, and prints a clear verdict
(SAFE TO PROMOTE / DO NOT PROMOTE / REVIEW NEEDED) before switching models —
see docs/retrain_policy.md for the full procedure.
