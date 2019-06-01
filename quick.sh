CUDA_VISIBLE_DEVICES='2, 3' python run_spatialstream.py --trained_model ~/PycharmProjects/egocentric-gaze-prediction/pretrained/spatial.pth.tar \
 --trained_late ~/PycharmProjects/egocentric-gaze-prediction/pretrained/late.pth.tar \
 --input ~/CharadesEgo_v1_rgb \
 --output ~/ego_attention/