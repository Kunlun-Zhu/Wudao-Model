# -*- encoding: utf-8 -*-
'''
@File    :   datasets.py
@Time    :   2021/01/11 21:01:51
@Author  :   Ming Ding 
@Contact :   dm18@mails.tsinghua.edu.cn
'''

# here put the import lib
import os
import sys
import math
import random
from tqdm import tqdm
import logging


import numpy as np
import torch
import torch.nn.functional as F
from torchvision import datasets, transforms
import pickle
from collections import namedtuple

from torch.utils.data import Dataset
import lmdb

from .unified_tokenizer import get_tokenizer
from .templates import TextCodeTemplate

logger = logging.getLogger(__name__)


class LMDBDataset(Dataset):
    def __init__(self, path, process_fn):
        self.env = lmdb.open(
            path,
            max_readers=32,
            readonly=True,
            lock=False,
            readahead=False,
            meminit=False,
        )
        self.process_fn = process_fn
        if not self.env:
            raise IOError('Cannot open lmdb dataset', path)

        with self.env.begin(write=False) as txn:
            self.length = int(txn.get('length'.encode('utf-8')).decode('utf-8'))

    def __len__(self):
        return self.length

    def __getitem__(self, idx):

        with self.env.begin(write=False) as txn:
            key = str(idx).encode('utf-8')

            row = pickle.loads(txn.get(key))

            return self.process_fn(row)
        

def get_dataset_by_type(dataset_type, path: str, args, DS_CLASS=LMDBDataset):       

    tokenizer = get_tokenizer()
    if args.finetune and args.max_position_embeddings_finetune > args.max_position_embeddings:
        ml = args.max_position_embeddings_finetune
    else:
        ml = args.max_position_embeddings

    def pad_to_len(ret):
        
        if len(ret) < ml: # pad
            return np.concatenate((ret, 
                np.array([tokenizer['[PAD]']] * (ml - len(ret)))),
                axis=0), len(ret)
        else:
            if len(ret) > ml:
                logger.warning('Out of max len, truncated.')
            return ret[:ml], ml

    if dataset_type == 'TokenizedDataset':
        # already tokenized when saved
        def process_fn(row):
            ret, attention_mask_sep = pad_to_len(row.flatten())
            return {'text': ret, 
                'loss_mask':  np.array([1] * attention_mask_sep + [0] * (len(ret) - attention_mask_sep))
                }

    elif dataset_type == 'TextCodeDataset':
        def process_fn(row):
            text, code = row[0], row[1].flatten()
            ret = TextCodeTemplate(text, code)
            ret, attention_mask_sep = pad_to_len(ret)
            return {'text': ret, 
                'loss_mask':  np.array([1] * attention_mask_sep + [0] * (len(ret) - attention_mask_sep))
                }
    return DS_CLASS(path, process_fn)

