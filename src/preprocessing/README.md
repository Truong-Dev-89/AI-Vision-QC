# preprocessing/
Crops the image to the ROI from the config, corrects tilt, normalizes
lighting/color before feeding it into the model. Every product shares the
same functions, differing only in the ROI parameters read from its YAML file.
