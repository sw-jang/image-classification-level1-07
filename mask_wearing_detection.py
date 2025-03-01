#!/usr/bin/env python3

from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

import torch

from facenet_pytorch import MTCNN

import cv2
import albumentations as A
from albumentations.pytorch import ToTensorV2

device = 'cuda' if torch.cuda.is_available() else 'cpu'
print('Using {} device'.format(device))


class InferenceMaskWearing:
    def __init__(self,
                 model1,
                 model2,
                 model1_weight=0.5,
                 model2_weight=0.5,
                 output_path='output',
                 crop_image_width=224,
                 crop_image_height=224) -> None:
        self.mtcnn = MTCNN(keep_all=True, device=device)
        self.model1 = model1
        self.model2 = model2
        self.model1_weight = model1_weight
        self.model2_weight = model2_weight
        self.crop_image_width = crop_image_width
        self.crop_image_height = crop_image_height
        self.output_path = output_path
        Path(f"{output_path}").mkdir(parents=True, exist_ok=True)

        self.swj_transfrom = A.Compose([
            A.Resize(width=self.crop_image_width,
                     height=self.crop_image_height),
            A.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
            ToTensorV2(),
        ])
        self.sdg_transfrom = A.Compose([
            A.Resize(width=self.crop_image_width,
                     height=self.crop_image_height),
            A.Normalize(mean=(0.55720607, 0.47626135, 0.44402045),
                        std=(0.2195448, 0.21720374, 0.22056428)),
            ToTensorV2(),
        ])

    def crop_image(self, img):
        """
        Only concern a single image input and Only one face detection.
        """

        boxes, _probs = self.mtcnn.detect(img)

        imgs = []
        for idx in range(len(boxes)):
            xmin = int(boxes[idx, 0]) - 30
            ymin = int(boxes[idx, 1]) - 30
            xmax = int(boxes[idx, 2]) + 30
            ymax = int(boxes[idx, 3]) + 30

            # if xmin < 0: xmin = 0
            # if ymin < 0: ymin = 0
            # if xmax > img.shape[0]: xmax = img.shape[0]
            # if ymax > img.shape[1]: ymax = img.shape[1]

            _img = img[ymin:ymax, xmin:xmax, :]

            _img = cv2.resize(
                _img,
                (self.crop_image_width, self.crop_image_height))  # Error 확인 필요
            imgs.append(_img)

        return imgs

    def result_plot(self, img, img_path, pred, prob):
        print(f'# RESULT - Pred. label: {pred:02d} (prob: {prob:.2f})')
        fig, ax = plt.subplots()
        ax.imshow(img)
        ax.text(
            x=0.5,
            y=0.1,
            s=f'Pred. label: {pred:02d} (prob: {prob:.2f})',
            fontsize=12,
            fontweight='bold',
            fontfamily='serif',
            transform=ax.transAxes,
            bbox=dict(facecolor='white', alpha=0.5, ec="none"),
            ha='center',
        )
        ax.axis(False)
        fig.tight_layout()
        fig.savefig(
            # f"{self.output_path}/{img_path.stem}.result{img_path.suffix}"
            img_path)
        plt.close(fig)

    def inference(self, img_path):
        img_path = Path(img_path)
        assert img_path.exists(), 'Image file not exists!'
        assert img_path.suffix in ['.jpg', '.jpeg',
                                   '.png'], 'Not allowed image format!'

        img = cv2.imread(img_path.__str__())
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        crop_imgs = self.crop_image(img)

        # Save cropped image.
        for idx, crop_img in enumerate(crop_imgs):
            file_name = f"{self.output_path}/{img_path.stem}.crop{idx}{img_path.suffix}"
            # plt.imsave(, crop_img)

            with torch.no_grad():
                # 수정 필요합니다.
                swj_img = self.swj_transfrom(
                    image=crop_img)['image'][None, :].to(device).float()
                sdg_img = self.sdg_transfrom(
                    image=crop_img)['image'][None, :].to(device).float()
                pred_from_model1 = self.model1(swj_img)
                pred_from_model2 = self.model2(sdg_img)
                # ensemble_pred is from hard-coded weights.
                ensemble_pred = self.model1_weight * pred_from_model1 + self.model2_weight * pred_from_model2
                final_pred = ensemble_pred.argmax(dim=-1).cpu().item()
                # all_predictions.extend(pred.cpu().numpy())

            self.result_plot(crop_img, file_name, final_pred,
                             ensemble_pred[0, final_pred])


if __name__ == '__main__':
    import argparse

    from model_pseudo_labeling.model import build_hybridViT
    from model_ViT_Large.sdg.model_normal import Classification_normal

    parser = argparse.ArgumentParser(description='')
    parser.add_argument('-i',
                        '--input-image',
                        metavar='DATA PATH',
                        type=str,
                        help='input data path')
    parser.add_argument('-m1',
                        '--model1',
                        metavar='DATA PATH',
                        type=str,
                        help='input model pth')
    parser.add_argument('-m2',
                        '--model2',
                        metavar='DATA PATH',
                        type=str,
                        help='input model pth')
    parser.add_argument('-o',
                        '--output',
                        metavar='FILE DIR NAME',
                        type=str,
                        default='test_output',
                        help='output directory name')
    args = parser.parse_args()

    model1 = build_hybridViT().to(device)
    model1_pth = '/opt/ml/5.pth'
    model1.load_state_dict(torch.load(model1_pth))
    model1.eval()

    model2 = Classification_normal(model_name='vit_large_patch16_224',
                                   device=device).to(device)
    model2_pth = '../model_vitL_3.pt'
    model2.load_state_dict(torch.load(model2_pth))
    model2.eval()

    inference_mask_wearing = InferenceMaskWearing(model1,
                                                  model2,
                                                  model1_weight=0.5,
                                                  model2_weight=0.5,
                                                  output_path=args.output)
    inference_mask_wearing.inference(args.input_image)
