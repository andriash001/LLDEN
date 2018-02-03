from __future__ import print_function

import os
import time
import shutil

import torch
import torch.nn as nn
# import torch.backends.cudnn as cudnn
import torch.optim as optim
from torch.utils.data import DataLoader
from torch.autograd import Variable
import torchvision.transforms as transforms
import torchvision.datasets as datasets
from progress.bar import Bar

from alexnet import AlexNet
from utils import *

# PATHS
CHECKPOINT    = "./checkpoints"
DATA          = "./data"

# BATCH
BATCH_SIZE    = 256
NUM_WORKERS   = 4

# SGD
LEARNING_RATE = 0.1
MOMENTUM      = 0.9
WEIGHT_DECAY  = 1e-4

# Step Decay
LR_DROP       = 0.5
EPOCHS_DROP   = 10

# MISC
EPOCHS        = 100
CUDA          = True

best_acc = 0  # best test accuracy

def main():
    global best_acc

    if not os.path.isdir(CHECKPOINT):
        os.makedirs(CHECKPOINT)

    print('==> Preparing dataset')

    dataloader = datasets.CIFAR100
    num_classes = 100

    transform_train = transforms.Compose([
        transforms.RandomCrop(32, padding=4),
        transforms.RandomHorizontalFlip(),
        transforms.ToTensor(),
        transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2023, 0.1994, 0.2010)),
    ])

    transform_test = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2023, 0.1994, 0.2010)),
    ])

    trainset = dataloader(root=DATA, train=True, download=True, transform=transform_train)
    trainloader = DataLoader(trainset, batch_size=BATCH_SIZE, shuffle=True, num_workers=NUM_WORKERS)

    testset = dataloader(root=DATA, train=False, download=False, transform=transform_test)
    testloader = DataLoader(testset, batch_size=BATCH_SIZE, shuffle=False, num_workers=NUM_WORKERS)

    print("==> Creating model")
    model = AlexNet(num_classes=100)

    if CUDA:
        model = model.cuda()

    print('    Total params: %.2fM' % (sum(p.numel() for p in model.parameters())/1000000.0))

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.SGD(model.parameters(), 
                    lr=LEARNING_RATE, 
                    momentum=MOMENTUM, 
                    weight_decay=WEIGHT_DECAY
                )

    for epoch in range(EPOCHS):

        adjust_learning_rate(optimizer, epoch + 1)

        print('\nEpoch: [%d | %d]' % (epoch + 1, EPOCHS))

        train_loss, train_acc = train(trainloader, model, criterion, optimizer )
        test_loss, test_acc = train(testloader, model, criterion, test = True )

        # save model
        is_best = test_acc > best_acc
        best_acc = max(test_acc, best_acc)
        save_checkpoint({
            'epoch': epoch + 1,
            'state_dict': model.state_dict(),
            'acc': test_acc,
            'optimizer': optimizer.state_dict()
            }, is_best)

    filepath_best = os.path.join(CHECKPOINT, "best.pt")
    checkpoint = torch.load(filepath_best)
    model.load_state_dict(checkpoint['state_dict'])

    #test_loss, test_acc = train(testloader, model, criterion, test = True )

    # scores = TODO
    # targets = TODO
    # area = AUROC(scores, targets)

def AUROC(scores, targets):
    """Calculates the Area Under the Curve.s
    Args:
        scores: Probabilities that target should be possitively classified.
        targets: 0 for negative, and 1 for positive examples.
    """
    # case when number of elements added are 0
    if scores.shape[0] == 0:
        return 0.5
    
    # sorting the arrays
    scores, sortind = torch.sort(torch.from_numpy(
        scores), dim=0, descending=True)
    scores = scores.numpy()
    sortind = sortind.numpy()

    # creating the roc curve
    tpr = np.zeros(shape=(scores.size + 1), dtype=np.float64)
    fpr = np.zeros(shape=(scores.size + 1), dtype=np.float64)

    for i in range(1, scores.size + 1):
        if targets[sortind[i - 1]] == 1:
            tpr[i] = tpr[i - 1] + 1
            fpr[i] = fpr[i - 1]
        else:
            tpr[i] = tpr[i - 1]
            fpr[i] = fpr[i - 1] + 1

    tpr /= (targets.sum() * 1.0)
    fpr /= ((targets - 1.0).sum() * -1.0)

    # calculating area under curve using trapezoidal rule
    n = tpr.shape[0]
    h = fpr[1:n] - fpr[0:n - 1]
    sum_h = np.zeros(fpr.shape)
    sum_h[0:n - 1] = h
    sum_h[1:n] += h
    area = (sum_h * tpr).sum() / 2.0

    return area

def train(batchloader, model, criterion, optimizer = None, test = False):
    
    # switch to train or evaluate mode
    if test:
        model.eval()
    else:
        model.train()

    batch_time = AverageMeter()
    data_time = AverageMeter()
    losses = AverageMeter()
    top1 = AverageMeter()
    top5 = AverageMeter()
    end = time.time()

    if test:
        bar = Bar('Testing', max=len(batchloader))
    else:
        bar = Bar('Training', max=len(batchloader))

    for batch_idx, (inputs, targets) in enumerate(batchloader):

        # measure data loading time
        data_time.update(time.time() - end)

        if CUDA:
            inputs = inputs.cuda()
            targets = targets.cuda()

        inputs = Variable(inputs)
        targets = Variable(targets)

        #compute output
        outputs = model(inputs)
        loss = criterion(outputs, targets)

        # measure accuracy and record loss
        prec1, prec5 = accuracy(outputs.data, targets.data, topk=(1, 5))
        losses.update(loss.data[0], inputs.size(0))
        top1.update(prec1[0], inputs.size(0))
        top5.update(prec5[0], inputs.size(0))

        if not test:
            # compute gradient and do SGD step
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        # measure elapsed time
        batch_time.update(time.time() - end)
        end = time.time()

        # plot progress
        bar.suffix  = '({batch}/{size}) Data: {data:.3f}s | Batch: {bt:.3f}s | Total: {total:} | ETA: {eta:} | Loss: {loss:.4f} | top1: {top1: .4f} | top5: {top5: .4f}'.format(
                    batch=batch_idx + 1,
                    size=len(batchloader),
                    data=data_time.avg,
                    bt=batch_time.avg,
                    total=bar.elapsed_td,
                    eta=bar.eta_td,
                    loss=losses.avg,
                    top1=top1.avg,
                    top5=top5.avg)
        bar.next()

    bar.finish()
    return (losses.avg, top1.avg)

def adjust_learning_rate(optimizer, epoch):
    global LEARNING_RATE

    if epoch % EPOCHS_DROP == 0:
        LEARNING_RATE *= LR_DROP
        for param_group in optimizer.param_groups:
            param_group['lr'] = LEARNING_RATE

def save_checkpoint(state, is_best):
    filepath = os.path.join(CHECKPOINT, "last.pt")
    torch.save(state, filepath)
    if is_best:
        filepath_best = os.path.join(CHECKPOINT, "best.pt")
        shutil.copyfile(filepath, filepath_best)

if __name__ == '__main__':
    main()
