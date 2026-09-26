# feedback/
The self-learning loop. Saves "suspect" images and images whose verdict was
corrected by an operator into the right data/raw/<product_id>/ subfolder.
Tracks when enough new data (min_new_samples in the config) has accumulated
to trigger an automatic retrain or prompt the operator to retrain manually.
