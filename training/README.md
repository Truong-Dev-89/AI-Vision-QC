# training/
train.py: trains the model for one product_id from images in
data/raw/<product_id>/good/
evaluate.py: evaluates a new model against the one currently in production
before switching over (avoids manual rollback if the new model is worse).
