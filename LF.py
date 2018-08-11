import torch
import torch.nn as nn
import numpy as np
from torch.utils.data import DataLoader
from scipy import ndimage
from skimage import io
import math
from tqdm import tqdm
import cv2, os

from floss import floss
from utils import *
from models.late_fusion import late_fusion
from lateDataset import lateDataset

class LF():
    def __init__(self, pretrained_model = None, save_path = 'save', late_save_img = 'loss_late.png',\
            save_name = 'best_late.pth.tar', device = '0', late_pred_path = '../new_pred', num_epoch = 10,\
            late_feat_path = '../new_feat', gt_path = '../gtea_gts', val_name = val_name, batch_size = 32,\
            loss_function = 'f'):
        self.model = late_fusion()
        self.device = torch.device('cuda:'+device)
        if pretrained_model is not None:
            pretrained_dict = torch.load(pretrained_model)
            model_dict = self.model.state_dict()
            model_dict.update(pretrained_dict)
            self.model.load_state_dict(model_dict)
            print('loaded pretrained late fusion model from '+ pretrained_model)
        self.model.to(device)
        self.batch_size = batch_size
        self.num_epoch = num_epoch
        listGtFiles = [k for k in os.listdir(gtPath) if val_name not in k]
        listGtFiles.sort()
        listValGtFiles = [k for k in os.listdir(gtPath) if val_name in k]
        listValGtFiles.sort()
        print('num of training LF samples: ', len(listGtFiles))


        imgPath_s = late_pred_path
        listTrainFiles = [k for k in os.listdir(imgPath_s) if val_name not in k]
        #listGtFiles = [k for k in os.listdir(gtPath) if val_name not in k]
        listValFiles = [k for k in os.listdir(imgPath_s) if val_name in k]
        #listValGtFiles = [k for k in os.listdir(gtPath) if val_name in k]
        listTrainFiles.sort()
        listValFiles.sort()
        print('num of LF val samples: ', len(listValFiles))

        featPath = late_feat_path
        listTrainFeats = [k for k in os.listdir(featPath) if val_name not in k]
        listValFeats = [k for k in os.listdir(featPath) if val_name in k]
        listTrainFeats.sort()
        listValFeats.sort()
        assert(len(listTrainFeats) == len(listTrainFiles))
        assert(len(listValGtFiles) == len(listValFiles))
        self.train_loader = DataLoader(dataset=lateDataset(imgPath_s, gtPath, featPath, listTrainFiles, listGtFiles, listTrainFeats), \
            batch_size = batch_size, shuffle=True, num_workers=0, pin_memory=True)
        self.val_loader = DataLoader(dataset=lateDataset(imgPath_s, gtPath, featPath, listValFiles, listValGtFiles, listValFeats), \
            batch_size = batch_size, shuffle=False, num_workers=0, pin_memory=True)
        if loss_function == 'f':
            self.criterion = floss().to(self.device)
        else:
            self.criterion = torch.nn.BCELoss().to(self.device)
        self.optimizer = torch.optim.Adam(self.model.parameters(), lr=1e-7)

    def trainLate(self):
        losses = AverageMeter()
        auc = AverageMeter()
        aae = AverageMeter()
        for i,sample in enumerate(self.train_loader):
            im = sample['im']
            gt = sample['gt']
            feat = sample['feat']
            im = im.float().to(self.device)
            gt = gt.float().to(self.device)
            feat = feat.float().to(self.device)
            out = self.model(feat, im)
            loss = self.criterion(out, gt)
            outim = out.cpu().data.numpy().squeeze()
            targetim = gt.cpu().data.numpy().squeeze()
            aae1, auc1, _ = computeAAEAUC(outim,targetim)
            auc.update(auc1)
            aae.update(aae1)
            losses.update(loss.item())
            self.optimizer.zero_grad()
            loss.backward()
            self.optimizer.step()
            if (i+1)%300 == 0:
                print('Epoch: [{0}][{1}/{2}]\t''AUCAAE_late {auc.avg:.3f} ({aae.avg:.3f})\t''Loss {loss.val:.4f} ({loss.avg:.4f})\t'.format(
                    epoch, i+1, len(loader)+1, auc = auc, loss= losses, aae=aae,))

        return losses.avg, auc.avg, aae.avg

    def testLate(self):
        losses = AverageMeter()
        auc = AverageMeter()
        aae = AverageMeter()
        with torch.no_grad():
            for i,sample in enumerate(self.val_loader):
                im = sample['im']
                gt = sample['gt']
                feat = sample['feat']
                im = im.float().to(self.device)
                gt = gt.float().to(self.device)
                feat = feat.float().to(self.device)
                out = self.model(feat, im)
                loss = self.criterion(out, gt)
                outim = out.cpu().data.numpy().squeeze()
                targetim = gt.cpu().data.numpy().squeeze()
                aae1, auc1, _ = computeAAEAUC(outim,targetim)
                auc.update(auc1)
                aae.update(aae1)
                losses.update(loss.item())
                if (i+1) % 1000 == 0:
                    print('Epoch: [{0}][{1}/{2}]\t''AUCAAE_late {auc.avg:.3f} ({aae.avg:.3f})\t''Loss {loss.val:.4f} ({loss.avg:.4f})\t'.format(
                        epoch, i+1, len(loader)+1, auc = auc, loss= losses, aae=aae,))

        return losses.avg, auc.avg, aae.avg

    def train(self):
        trainprev = 999
        valprev = 999
        loss_train = []
        loss_val = []
        for epoch in range(self.num_epoch):
            loss, auc, aae = train_late(epoch, train_loader, model_late, criterion, optimizer_late)
            loss_train.append(loss)
            print('training, auc is %5f, aae is %5f'%(auc, aae))
            if loss < trainprev:
                torch.save({'state_dict': model_late.state_dict(), 'loss': loss, 'auc': auc, 'aae': aae}, os.path.join(args.save_path, args.save_late))
                trainprev = loss

            loss, auc, aae = val_late(epoch, val_loader, model_late, criterion)
            loss_val.append(loss)
            plot_loss(loss_train, loss_val, os.path.join(args.save_path, args.late_save_img))
            if loss < valprev:
                torch.save({'state_dict': model_late.state_dict(), 'loss': loss, 'auc': auc, 'aae': aae}, os.path.join(args.save_path, 'val'+args.save_late))
                valprev = loss