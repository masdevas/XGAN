import shap
import os
import pandas as pd
import numpy as np
import torch
import gc
import json

import matplotlib.pyplot as plt

import warnings
warnings.filterwarnings("ignore")

from xgan.utils import prepare_batches

class FullGAN(torch.nn.Module):
    def __init__(self, generator, classifier, device):
        super().__init__()
        self.generator = generator
        self.classifier = classifier
        self.device = device
        self.cpu = torch.device('cpu')

    def forward(self, x):
        x = torch.from_numpy(x).float().to(self.cpu)
        self.generator.to(self.cpu)
        generator_out = self.generator(x)
        generator_out = generator_out.reshape(generator_out.shape[0], -1).detach().cpu().numpy()
        result = self.classifier.predict_proba(generator_out)
        del generator_out
        self.generator.to(self.device)
        return result

class ShapGen:
    def __init__(self, gan, generator, classifier):
        self.gan = gan
        self.full_gan = FullGAN(generator, classifier, gan.device)

    def __del__(self):
        del self.full_gan

    def _generate_features(self, sample_shape):
        features = []
        for index in np.ndindex(sample_shape):
            features.append('x'.join([str(value) for value in index]))
        return features

    def generate_data_for_ml(self, data, labels, batch_size):
        X_list = []
        y_list = []
        real_batch_generator = prepare_batches(data, labels, batch_size)
        for batch_idx, (batch_data, batch_labels) in real_batch_generator:
            batch_data = batch_data.to(self.gan.device)
            self.features = self._generate_features(batch_data[0].shape)
            batch_data = batch_data.reshape(batch_data.shape[0], -1)
            X_list.append(batch_data.cpu().numpy())
            y_list.append(batch_labels.cpu().numpy())
        
        X = np.concatenate(X_list)
        y = np.concatenate(y_list)
        
        del batch_data, batch_labels
        return X, y

    def fit_ml(self, X, y):
        self.full_gan.classifier.fit(X, y)

    def explain(self, shap_gen_config, noize_getter, test_samples, columns, result_dir):
        with torch.no_grad():
            shap_dir = os.path.join(result_dir, 'shap')
            os.makedirs(shap_dir)
            
            # Train SHAP
            def predict(X):
                return self.full_gan.forward(X)
            background_samples = noize_getter(shap_gen_config['background_samples_to_gen'])
            e = shap.KernelExplainer(predict, background_samples)

            # Get predictions for test data
            test_predicted = predict(test_samples)
            predicted_dict = pd.DataFrame(data=test_predicted, columns=['class_'+str(idx) for idx in range(test_predicted.shape[1])], index=['sample_'+str(idx) for idx in range(test_predicted.shape[0])]).to_dict(orient='index')
            with open(os.path.join(shap_dir, 'shap_test_probs.json'), 'w') as f:
                f.write(json.dumps(predicted_dict, indent=4, sort_keys=True))

            # Save generated data
            # generator_out = self.full_gan.generator(torch.from_numpy(test_samples).float().to(self.gan.device))
            # self.gan._save_images(generator_out, shap_dir, 'shap_test_generated', generator_out.shape[0])

            test_samples_pd = pd.DataFrame(data=test_samples, columns=columns)
            shap_values = e.shap_values(test_samples_pd, nsamples=shap_gen_config['shap_nsamples'], silent=True)
            for class_idx, class_shap_values in enumerate(shap_values):
                if 'summary' in shap_gen_config['features']:
                    shap.summary_plot(class_shap_values, test_samples_pd, show=False)
                    plt.savefig(os.path.join(shap_dir, f'class_{class_idx}_summary.png'))
                    plt.cla()
                    plt.clf()
                    plt.close()
                del class_idx, class_shap_values

            if 'waterfall' in shap_gen_config['features']:
                waterfall_dir = os.path.join(shap_dir, 'waterfall')
                os.makedirs(waterfall_dir)
                for class_idx, class_shap_values in enumerate(shap_values):
                    waterfall_class_dir = os.path.join(waterfall_dir, f'class_{class_idx}')
                    os.makedirs(waterfall_class_dir)
                    for sample_idx in range(test_samples.shape[0]):
                        shap.waterfall_plot(shap.Explanation(values=class_shap_values[sample_idx,:], base_values=e.expected_value[class_idx], data=test_samples[sample_idx], feature_names=columns), show=False)
                        fig = plt.gcf()
                        fig.set_size_inches(18, 10, forward=True)
                        fig.savefig(os.path.join(waterfall_class_dir, f'{sample_idx}_waterfall_plot.png'))
                        plt.cla()
                        plt.clf()
                        plt.close()
                    del class_idx, class_shap_values, waterfall_class_dir
        del shap_dir, background_samples, predict, e, test_predicted, predicted_dict, test_samples_pd, shap_values
