from __future__ import print_function, division

import torch
import torchvision
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.autograd import Variable
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms, utils

import pandas as pd
from skimage import io, transform
import numpy as np 
import scipy
import scipy.misc
import time
import os
import math
import sys 
import pyexr
from random import shuffle
from sklearn.feature_extraction.image import extract_patches


class MatNet(nn.Module):
	def __init__(self):
		super(MatNet, self).__init__()
		# Material network based on http://openaccess.thecvf.com/content_ICCV_2017/supplemental/Liu_Material_Editing_Using_ICCV_2017_supplemental.pdf
		self.conv1 = nn.Conv2d(6   , 16  , 3, padding=1)
		self.conv2 = nn.Conv2d(16  , 32  , 3, padding=1)
		self.conv3 = nn.Conv2d(32  , 64  , 3, padding=1) 
		self.conv4 = nn.Conv2d(64  , 128 , 3, padding=1)
		self.conv5 = nn.Conv2d(128 , 256 , 3, padding=1)
		self.conv6 = nn.Conv2d(256 , 512 , 3, padding=1)  
		self.conv7 = nn.Conv2d(512 , 1024, 3, padding=1)
		#self.conv8 = nn.Conv2d(1024, 2048, 3, padding=1)
		self.fc8   = nn.Linear(1024, 3)

	
	def forward(self, x):
    		# x -> 3 x 256 x 256
		x, self.pool_idx1 = F.max_pool2d(F.relu(self.conv1(x)), kernel_size=2, return_indices=True) 
		# x -> 16 x 128 x 128
		x, self.pool_idx2 = F.max_pool2d(F.relu(self.conv2(x)), kernel_size=2, return_indices=True)
		# x -> 32 x 64 x 64
		x, self.pool_idx3 = F.max_pool2d(F.relu(self.conv3(x)), kernel_size=2, return_indices=True)
		# x -> 64 x 32 x 32
		x, self.pool_idx4 = F.max_pool2d(F.relu(self.conv4(x)), kernel_size=2, return_indices=True)
		# # x -> 128 x 16 x 16
		x, self.pool_idx5 = F.max_pool2d(F.relu(self.conv5(x)), kernel_size=2, return_indices=True)
		# # x -> 256 x 8 x 8
		x, self.pool_idx6 = F.max_pool2d(F.relu(self.conv6(x)), kernel_size=2, return_indices=True)
		# # x -> 512 x 4 x 4
		x, self.pool_idx7 = F.max_pool2d(F.relu(self.conv7(x)), kernel_size=2, return_indices=True) 
		#x, self.pool_idx8 = F.max_pool2d(F.relu(self.conv8(x)), kernel_size=2, return_indices=True)
		# x -> 1024 x 2 x 2
		x = x.view(-1, self.num_flat_features(x))
		x = self.fc8(x)

		return x


	def num_flat_features(self, x):
		size = x.size()[1:]  # all dimensions except the batch dimension
		num_features = 1
		for s in size:
			num_features *= s
		return num_features

class AllShapeDataset(Dataset):
	def __init__(self, csv_file, root_dir, info_dir, env_dir, transform=None):
				self.data_frame = pd.read_csv(csv_file)
				self.root_dir   = root_dir
				self.info_dir   = info_dir
				self.env_dir   = env_dir				
				self.transform  = transform
	def __len__(self):
		return len(self.data_frame)
	def __getitem__(self, idx):
  		
			input     = np.zeros(shape = (128, 128, 6))

			img_fn    = os.path.join(self.root_dir, self.data_frame.ix[idx, 0])
			luminance = pyexr.open(img_fn).get() # luminance 

			#env_fn    = os.path.join(self.env_dir, self.data_frame.ix[idx, 2] + '_normalized.exr')
			#env       = (pyexr.open(env_fn).get() + 2716.7) / (81743 + 2716.7) # envmaps
			env_fn    = os.path.join(self.env_dir, 'env' + str(self.data_frame.ix[idx, 2]) + '.exr')
			env       = pyexr.open(env_fn).get('360.00-830.00nm') /5.5404 #17651 # envmaps

			nor_fn    = os.path.join(self.info_dir, self.data_frame.ix[idx, 1] + '_default.exr')
			geometry  = pyexr.open(nor_fn)

			normal_R  = (geometry.get('normal.R') + 1)/2 # normal.x
			normal_G  = (geometry.get('normal.G') + 1)/2 # normal.y
			normal_B  = (geometry.get('normal.B') + 1)/2 # normal.z
			depth     = (geometry.get('distance.Y') - 30) / (37-30)


			#normal_R  = geometry.get('1') # normal.x
			#normal_G  = geometry.get('2') # normal.y
			#normal_B  = geometry.get('3') # normal.z
			#depth     = geometry.get('0')

			shape 	  = self.data_frame.ix[idx, 1]
			light 	  = self.data_frame.ix[idx, 2]
			#envmap     = (geometry.get('distance.Y') - 30) / (37-30)

			#sigmaT 	  = self.data_frame.ix[idx, 3].astype('float') / 300 # normalize
			sigmaT 	  = self.data_frame.ix[idx, 3].astype('float')
			albedo    = self.data_frame.ix[idx, 4].astype('float')
			hg        = self.data_frame.ix[idx, 5].astype('float') 

			patches_envmap_R = extract_patches(env[:,:,0], patch_shape=(2, 4), extraction_step=(2, 4))
			#patches_envmap_G = extract_patches(env[:,:,1], patch_shape=(1, 2), extraction_step=(1, 2))
			#patches_envmap_B = extract_patches(env[:,:,2], patch_shape=(1, 2), extraction_step=(1, 2))


			patches_luminance = extract_patches(luminance[:,:,0], patch_shape=(4, 4), extraction_step=(4, 4))
			input[:,:,0] = patches_luminance.mean(-1).mean(-1)
			input[:,:,1] = normal_R[:,:,0]
			input[:,:,2] = normal_G[:,:,0]
			input[:,:,3] = normal_B[:,:,0]
			input[:,:,4] = depth[:,:,0]
			input[:,:,5] = patches_envmap_R.mean(-1).mean(-1)
			#input[:,:,6] = patches_envmap_G.mean(-1).mean(-1)
			#input[:,:,7] = patches_envmap_B.mean(-1).mean(-1)

			target = torch.from_numpy(patches_luminance.mean(-1).mean(-1)).unsqueeze(0)

			input = input.transpose((2, 0, 1))
			input = torch.from_numpy(input)

			params    = torch.Tensor(3)
			params[0] = sigmaT
			params[1] = albedo 
			params[2] = hg 

			sample = {
					'input' : input,
					'params': params,
					'target' : target,
					'shape' : shape,
					'light' : light,
					'sigmaT' : sigmaT,
					'albedo' : albedo,
					'hg' : hg,
					'fn' : self.data_frame.ix[idx, 0]
			}

			return sample



five_shape_ten_light_train_dataset = AllShapeDataset(
																		csv_file='GfxMLForInverse_datasets_full/csvfiles_angles/lucy_Inv.csv',
																		root_dir='/phoenix/S6/chec/dataset_s2b_blur_test_mean1/',
																		info_dir='GfxMLForInverse_datasets_full/sceneinfo_128/',
																		env_dir='GfxMLForInverse_datasets_full/envmap_sunsky_blur/'
																)


data_train_loader = DataLoader(five_shape_ten_light_train_dataset, 
							   batch_size=1, 
							   shuffle=False, 
							   num_workers=0)



def loadFigure(filename):
    	try:
		tmp = pyexr.open(filename)
		return tmp

	except Exception as e:
		return None


test = torch.load('/phoenix/S6/chec/results/data_allshapes_blur/ave1/e0_30_60_90_train_ITN/ITN239.bin')
net = test['model']



class MitsubaLossFunction(torch.autograd.Function):
	def __init__(self):
		super(MitsubaLossFunction, self).__init__()

	def forward(self, input, tmp_img, tmp_grad_sigmaT, tmp_grad_albedo, tmp_grad_hg, gt_img):
  		
		diff = 28.2486*tmp_img - gt_img
		self.save_for_backward(input, tmp_img.float(), tmp_grad_sigmaT.float(), tmp_grad_albedo.float(), tmp_grad_hg.float(), gt_img.float())
		loss = torch.Tensor(1, 1)
		loss[0][0] = torch.pow(diff, 2).mean()

		return loss

	def backward(self, grad_out):
		input, tmp_img,tmp_grad_sigmaT, tmp_grad_albedo, tmp_grad_hg, gt_img = self.saved_tensors
		diff = 28.2486*tmp_img - gt_img
		grad_in = torch.Tensor(input.size()).float()

		grad_in[0] = (diff  * tmp_grad_sigmaT).mean() * grad_out.clone()[0][0]
		grad_in[1] = (diff  * tmp_grad_albedo).mean() * grad_out.clone()[0][0]
		grad_in[2] = (diff  * tmp_grad_hg).mean() * grad_out.clone()[0][0]


		return grad_in, None, None, None, None, None



class MitsubaLossModule(torch.nn.Module):
	def __init__(self):
		super(MitsubaLossModule, self).__init__()

	def forward(self, input, tmp_img,tmp_grad_sigmaT, tmp_grad_albedo, tmp_grad_hg,  gt_img):
		return MitsubaLossFunction()(input, tmp_img, tmp_grad_sigmaT, tmp_grad_albedo, tmp_grad_hg, gt_img)

totalloss = []
totalSigmaT = []
totalAlbedo = []
totalG = []
theta = 30
nsamples = 512
#Starting validation
print('starting validation ... ... ... ... ... ...')
criterion_MTS = MitsubaLossModule()
num_epochs = 250
print(len(five_shape_ten_light_train_dataset))
for i in range(len(five_shape_ten_light_train_dataset)):
	print('----------------------------------------------------------')
	print(i)
	# input 5-channel images
	sample = five_shape_ten_light_train_dataset[i]	
	input = Variable(sample['input'].float()).unsqueeze(0)
	output1 = net.forward(input)

	gt_params = sample['params']
	print(gt_params[0])
	print(gt_params[1])
	print(gt_params[2])
	print(sample['fn'])
	params = torch.Tensor(3)
	params[0] = output1.data[0][0]
	params[1] = output1.data[0][1]
	params[2] = output1.data[0][2]
	target_batch = sample['target'].float()

	#gt = Variable(target_batch)
	shape = sample['shape']
	light = sample['light']
	xml_fn = shape + '_sunsky.xml'


	params_new = Variable(params, requires_grad = True)
	optimizer = optim.Adam([params_new], lr = 0.01)
	
	allloss = []
	allSigmaT = []
	allAlbedo = []
	allG = []

	


	for j in range(2):

		
		sigmaT_ac = np.clip(params_new.data[0], np.log(20.0), np.log(300.0)) #torch.clamp(params[0], 10.0, 300.0)
		albedo_ac = np.clip(params_new.data[1], 0.35, 0.97)  #torch.clamp(params[1], 0.05, 0.95)
		g_ac = np.clip(params_new.data[2], -0.1, 0.9)  #torch.clamp(params[2], -0.2, 0.9)
		optimizer.param_groups[0]['params'][0].data[0] = sigmaT_ac
		optimizer.param_groups[0]['params'][0].data[1] = albedo_ac
		optimizer.param_groups[0]['params'][0].data[2] = g_ac


		sigmT_afterexp = torch.exp(params_new[0])
		rest_pred = params_new[1:]
		adterEXP_pred_clamped = torch.cat((sigmT_afterexp, rest_pred))

		fi = int(light)
		xValue = math.sin(math.radians(theta))*math.cos(math.radians(fi))
		zValue = math.sin(math.radians(theta))*math.sin(math.radians(fi))
		yValue = math.cos(math.radians(theta))



		
		
		cmd = 'cd ~/mitsuba/dist && ./mitsuba_AD ~/GfxMLForInverse/GfxMLForInverse_datasets_full/scenesAD_sunsky_maxDepth200/'+xml_fn+' -Dmeshmodel='+shape +' -Dx='+str(xValue) +' -Dy='+str(yValue)+' -Dz='+str(zValue) + ' -DsigmaT='+str(adterEXP_pred_clamped.data[0])+' -Dalbedo='+str(adterEXP_pred_clamped.data[1])+' -Dg=' + str(adterEXP_pred_clamped.data[2])+' -DnumSamples='+str(nsamples)+' -p 32 -q -o ~/GfxMLForInverse/tmp.exr'



		#cmd = 'mitsuba_AD GfxMLForInverse_datasets/scenesAD/'+xml_fn+' -Dmeshmodel='+shape+' -DsigmaT='+str(adterEXP_pred_clamped.data[0])+' -Dalbedo='+str(adterEXP_pred_clamped.data[1])+' -Dg=' + str(adterEXP_pred_clamped.data[2])+' -DnumSamples='+str(nsamples)+' -o tmp/tmp.exr -q'

		#os.system('mitsuba_AD GfxMLForInverse_datasets/scenesAD/'+xml_fn+' -Dmeshmodel='+shape+' -DsigmaT='+str(adterEXP_pred_clamped.data[0])+' -Dalbedo='+str(adterEXP_pred_clamped.data[1])+' -Dg=' + str(adterEXP_pred_clamped.data[2])+' -DnumSamples='+str(nsamples)+' -o tmp.exr -q')
		os.system(cmd)
		tmp  = pyexr.open('tmp.exr')
		batch_result_fwd = torch.from_numpy(tmp.get('Forward'))[:,:,0].unsqueeze(0)
		batch_result_sigmaT = torch.from_numpy(tmp.get('sigmaT'))[:,:,0].unsqueeze(0)
		batch_result_albedo = torch.from_numpy(tmp.get('albedo'))[:,:,0].unsqueeze(0)
		batch_result_hg = torch.from_numpy(tmp.get('g'))[:,:,0].unsqueeze(0)



		gt_img_var = Variable(target_batch)
		tmp_img_var = Variable(batch_result_fwd)
		tmp_grad_sigmaT_var = Variable(batch_result_sigmaT)
		tmp_grad_albedo_var = Variable(batch_result_albedo)
		tmp_grad_hg_var = Variable(batch_result_hg)

		loss = criterion_MTS(adterEXP_pred_clamped, tmp_img_var, tmp_grad_sigmaT_var, tmp_grad_albedo_var, tmp_grad_hg_var, gt_img_var)
		#loss = criterion_MTS(adterEXP_pred_clamped, forward, grad_sigmaT, grad_albedo, grad_hg, gt)

		print('loss = ', loss.data[0][0], ' pred sigmaT = ', adterEXP_pred_clamped.data[0], ' albedo = ', adterEXP_pred_clamped.data[1], ' hg = ', adterEXP_pred_clamped.data[2])
		
		allSigmaT += [adterEXP_pred_clamped.data[0]]
		allAlbedo += [adterEXP_pred_clamped.data[1]]
		allG += [adterEXP_pred_clamped.data[2]]
		allloss += [loss.data[0][0]]
		optimizer.zero_grad()
		loss.backward()
		optimizer.step()
	totalloss += [allloss]
	totalSigmaT += [allSigmaT]
	totalAlbedo += [allAlbedo]
	totalG += [allG]
		# for c in range(3):
    	# 		params[c] = params_new.data[c]
	print(totalSigmaT)
	print(totalAlbedo)
	print(totalG)
	print(totalloss)	
	np.save('/phoenix/S6/chec/results/InvErrors/ITN/'+shape+'/SigmaT.npy', np.array(totalSigmaT))
	np.save('/phoenix/S6/chec/results/InvErrors/ITN/'+shape+'/albedo.npy', np.array(totalAlbedo))
	np.save('/phoenix/S6/chec/results/InvErrors/ITN/'+shape+'/g.npy', np.array(totalG))
	np.save('/phoenix/S6/chec/results/InvErrors/ITN/'+shape+'/loss.npy', np.array(totalloss))
	