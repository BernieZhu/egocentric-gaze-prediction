import torch
import torch.nn as nn
from torch.utils.data import DataLoader
import torch.utils.model_zoo as model_zoo
from data.STdatas import STDataset
import os
import time
import numpy as np
from utils import *
from floss import floss
import math
from tqdm import tqdm
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--lr', type=float, default=1e-7, required=False)
parser.add_argument('--loss_save', default='loss_spatial.png', required=False)
parser.add_argument('--save_name', default='_spatial.pth.tar', required=False)
parser.add_argument('--save_path', default='save', required=False)
parser.add_argument('--loss_function', default='f', required=False)
parser.add_argument('--num_epoch', type=int, default=10, required=False)
parser.add_argument('--device', default='0')
parser.add_argument('--resume', type=int, default=0, help='0 from vgg, 1 from pretrained model.')
parser.add_argument('--pretrained_model', default='save/best_spatial.pth.tar', help='path to pretrained model')
parser.add_argument('--batch_size', type=int, default=16, required=False)
parser.add_argument('--flowPath', default='../gtea_imgflow', required=False)
parser.add_argument('--imagePath', default='../gtea_images', required=False)
parser.add_argument('--fixsacPath', default='../fixsac', required=False)
parser.add_argument('--gtPath', default='../gtea_gts', required=False)
parser.add_argument('--val_name', default='Alireza', required=False)
args = parser.parse_args()

device = torch.device('cuda:'+args.device)

imgPath_s = args.imagePath
imgPath = args.flowPath
fixsacPath = args.fixsacPath
gtPath = args.gtPath
listFolders = [k for k in os.listdir(imgPath)]
listFolders.sort()
listGtFiles = [k for k in os.listdir(gtPath) if args.val_name not in k]
listGtFiles.sort()
listValGtFiles = [k for k in os.listdir(gtPath) if args.val_name in k]
listValGtFiles.sort()
print('num of training samples: ', len(listGtFiles))

listfixsacTrain = [k for k in os.listdir(fixsacPath) if args.val_name not in k]
listfixsacVal = [k for k in os.listdir(fixsacPath) if args.val_name in k]
listfixsacVal.sort()
listfixsacTrain.sort()

listTrainFiles = [k for k in os.listdir(imgPath_s) if args.val_name not in k]
listValFiles = [k for k in os.listdir(imgPath_s) if args.val_name in k]

listTrainFiles.sort()
listValFiles.sort()
print('num of val samples: ', len(listValFiles))
STTrainData = STDataset(imgPath, imgPath_s, gtPath, listFolders, listTrainFiles, listGtFiles, listfixsacTrain, fixsacPath)

STValData = STDataset(imgPath, imgPath_s, gtPath, listFolders, listValFiles, listValGtFiles, listfixsacVal, fixsacPath)
SpatialTrainLoader = DataLoader(dataset=STTrainData, batch_size=args.batch_size, shuffle=True, num_workers=0, pin_memory=True)

SpatialValLoader = DataLoader(dataset=STValData, batch_size=args.batch_size, shuffle=False, num_workers=0, pin_memory=True)

class VGG(nn.Module):
    
    def __init__(self, features):
        super(VGG, self).__init__()
        self.features = features
        for param in self.features.parameters():
            param.requires_grad = False
        self.decoder = nn.Sequential(nn.Conv2d(512, 512, kernel_size=3, padding=1),
                                        nn.ReLU(inplace=True),
                                        nn.Conv2d(512, 512, kernel_size=3, padding=1),
                                        nn.ReLU(inplace=True),
                                        nn.Conv2d(512, 512, kernel_size=3, padding=1),nn.ReLU(inplace=True),
                                        nn.Upsample(scale_factor=2),
                                        nn.Conv2d(512, 512, kernel_size=3, padding=1),nn.ReLU(inplace=True),
                                        nn.Conv2d(512, 512, kernel_size=3, padding=1),nn.ReLU(inplace=True),
                                        nn.Conv2d(512, 512, kernel_size=3, padding=1),nn.ReLU(inplace=True),
                                        nn.Upsample(scale_factor=2),
                                        nn.Conv2d(512, 256, kernel_size=3, padding=1),nn.ReLU(inplace=True),
                                        nn.Conv2d(256, 256, kernel_size=3, padding=1),nn.ReLU(inplace=True),
                                        nn.Conv2d(256, 256, kernel_size=3, padding=1),nn.ReLU(inplace=True),
                                        nn.Upsample(scale_factor=2),
                                        nn.Conv2d(256, 128, kernel_size=3, padding=1),nn.ReLU(inplace=True),
                                        nn.Conv2d(128, 128, kernel_size=3, padding=1),nn.ReLU(inplace=True),
                                        nn.Upsample(scale_factor=2),
                                        nn.Conv2d(128, 64, kernel_size=3, padding=1),nn.ReLU(inplace=True),
                                        nn.Conv2d(64, 64, kernel_size=3, padding=1),nn.ReLU(inplace=True),
                                        nn.Conv2d(64, 1, kernel_size=1, padding=0),
                                        )

        self.final = nn.Sigmoid()
        self._initialize_weights()

    def forward(self, x):
        x = self.features(x)
        x = self.decoder(x)
        y = self.final(x)
        return y
    
    def _initialize_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                n = m.kernel_size[0] * m.kernel_size[1] * m.out_channels
                m.weight.data.normal_(0, math.sqrt(2. / n))
                if m.bias is not None:
                    m.bias.data.zero_()
            elif isinstance(m, nn.BatchNorm2d):
                m.weight.data.fill_(1)
                m.bias.data.zero_()
            elif isinstance(m, nn.Linear):
                n = m.weight.size(1)
                m.weight.data.normal_(0, 0.01)
                m.bias.data.zero_()



def save_checkpoint(state,filename,save_path):
    torch.save(state, os.path.join(save_path, filename))


def train(train_loader, model, criterion, optimizer, epoch):
    batch_time = AverageMeter()
    losses = AverageMeter()
    model.train()
    end = time.time()
    optimizer.zero_grad()
    loss_mini_batch = 0.0
    for i, sample in tqdm(enumerate(train_loader)):
        input = sample['image']
        target = sample['gt']
        input = input.float().to(device)
        target = target.float().to(device)
        output = model(input)
        target = target.view(output.size())
        loss = criterion(output, target)
        loss_mini_batch += loss.item()
        loss.backward()
        optimizer.step()
        optimizer.zero_grad()
        losses.update(loss_mini_batch, input.size(0))
        batch_time.update(time.time() - end)
        end = time.time()
        loss_mini_batch = 0
        if (i+1) % 5000 ==0:
            print('Epoch: [{0}][{1}/{2}]\t'
          'Time {batch_time.val:.3f} ({batch_time.avg:.3f})\t'
          'Loss {loss.val:.4f} ({loss.avg:.4f})\t'.format(epoch, i+1, len(train_loader)+1, batch_time=batch_time, loss=losses))
    return losses.avg


def validate(val_loader, model, criterion, epoch):
    batch_time = AverageMeter()
    losses = AverageMeter()
    aae = AverageMeter()
    auc = AverageMeter()
    model.eval()
    end = time.time()
    with torch.no_grad():
        for i, sample in tqdm(enumerate(val_loader)):
            input = sample['image']
            target = sample['gt']
            input = input.float().to(device)
            target = target.float().to(device)
            output = model(input)
            target = target.view(output.size())
            loss = criterion(output, target)
            losses.update(loss.item(), input.size(0))
            outim = output.cpu().data.numpy().squeeze()
            targetim = target.cpu().data.numpy().squeeze()
            aae1, auc1, _ = computeAAEAUC(outim, targetim)
            auc.update(auc1)
            aae.update(aae1)
            batch_time.update(time.time() - end)
            end = time.time()

            if (i+1) % 1000 == 0:
                print('Test: [{0}/{1}]\t'
                      'Time {batch_time.val:.3f} ({batch_time.avg:.3f})\t'
                      'Loss {loss.val:.4f} ({loss.avg:.4f})\t'.format(i, len(val_loader), batch_time=batch_time, loss=losses,))
    print ('AUC: {0}\t AAE: {1}'.format(auc.avg, aae.avg))
    return losses.avg


# main

if args.resume == 1:
    print('building model and loading from pretrained model...')
    model = VGG(make_layers(cfg['D'], 3))
    trained_model = args.pretrained_model
    pretrained_dict = torch.load(trained_model)
    pretrained_dict = pretrained_dict['state_dict']
    model_dict = model.state_dict()
    model_dict.update(pretrained_dict)
    model.load_state_dict(model_dict)
    model.to(device)
    print('done!')
else:
    print('building model and loading pretrained_dict from vgg...')
    model = VGG(make_layers(cfg['D'], 3))
    pretrained_dict = model_zoo.load_url('https://download.pytorch.org/models/vgg16_bn-6c64b313.pth')
    model_dict = model.state_dict()
    pretrained_dict = {k: v for k,v in pretrained_dict.items() if k in model_dict}
    model_dict.update(pretrained_dict)
    model.load_state_dict(model_dict)
    model.to(device)
    print('done!')


if args.loss_function != 'f':
    criterion = torch.nn.BCELoss().to(device)
else:
    criterion = floss().to(device)
optimizer = torch.optim.Adam(model.decoder.parameters(), lr=args.lr)

if not os.path.exists(args.save_path):
    os.makedirs(args.save_path)


# Training and testing loop
train_loss = []
val_loss = []
best_loss = 100
for epoch in range(args.num_epoch):
    loss1 = train(SpatialTrainLoader, model, criterion, optimizer, epoch)
    train_loss.append(loss1)
    loss1 = validate(SpatialValLoader, model, criterion, epoch)
    val_loss.append(loss1)
    plot_loss(train_loss, val_loss, os.path.join(args.save_path, args.loss_save))
    print('epoch%05d, val loss is: %05f' % (epoch, loss1))
    if loss1 < best_loss:
        best_loss = loss1
        save_checkpoint({'epoch': epoch, 'arch': 'rgb', 'state_dict': model.state_dict(), 'optimizer': optimizer.state_dict(),},
                            '%05d'%epoch+args.save_name, args.save_path)















