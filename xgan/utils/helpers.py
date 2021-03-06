import gc
import numpy as np

from collections import OrderedDict
from torch.utils.data import BatchSampler, RandomSampler
import torch

from .exception import XAIConfigException

gan_labels = OrderedDict(sorted({ 'real': 1., 'fake': 0. }.items(), key=lambda x:x[1]))

def check_for_key(config, key, value=None):
    if value is None:
        if config is not None and key in config.keys():
            return config[key]
        else:
            return None
    else:
        if config is not None and key in config.keys():
            if config[key] == value:
                return True
            else:
                raise Exception(f'Unknown parameter \'{key}\' in explanation_config : {value}')
        else:
            return False

def _create_batch_generator(data_loader):
    for index, (data, target) in enumerate(data_loader):
        yield index, (data, target)

def _create_tensor_batch_generator(data, labels, indices):
    for batch_idx, samples_indices in enumerate(indices):
        batch_data = data[samples_indices]
        if labels is None:
            yield batch_idx, (batch_data, None)
        else:
            batch_labels = labels[samples_indices]
            yield batch_idx, (batch_data, batch_labels)

def prepare_batches(data, labels, batch_size):
    if isinstance(data, torch.Tensor):
        indices = BatchSampler(RandomSampler(range(data.shape[0])), batch_size=batch_size, drop_last=False)
        batch_generator = _create_tensor_batch_generator(data, labels, indices)
    else:
        dataloader = torch.utils.data.DataLoader(data, batch_size=batch_size, shuffle=True)
        batch_generator = _create_batch_generator(dataloader)
    return batch_generator

flush_data_limits = {'default' : 1.}

def _flush_data(value, limit):
    if value < limit:
        gc.collect()
        torch.cuda.empty_cache()

def flush_data(funcname='default'):
    value = np.random.uniform(low=0., high=1.)
    _flush_data(value, flush_data_limits[funcname])

def set_flush_data_limit(funcname, limit):
    global flush_data_limits
    flush_data_limits[funcname] = limit