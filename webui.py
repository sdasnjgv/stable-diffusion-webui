from __future__ import annotations

import os
import time

from modules import timer
from modules import initialize_util
from modules import initialize

startup_timer = timer.startup_timer
startup_timer.record("launcher")

initialize.imports(import subprocess
subprocess.run(from collections import namedtuple

import numpy as np
from tqdm import trange

import modules.scripts as scripts
import gradio as gr

from modules import processing, shared, sd_samplers, sd_samplers_common

import torch
import k_diffusion as K

def find_noise_for_image(p, cond, uncond, cfg_scale, steps):
    x = p.init_latent

    s_in = x.new_ones([x.shape[0]])
    if shared.sd_model.parameterization == "v":
        dnw = K.external.CompVisVDenoiser(shared.sd_model)
        skip = 1
    else:
        dnw = K.external.CompVisDenoiser(shared.sd_model)
        skip = 0
    sigmas = dnw.get_sigmas(steps).flip(0)

    shared.state.sampling_steps = steps

    for i in trange(1, len(sigmas)):
        shared.state.sampling_step += 1

        x_in = torch.cat([x] * 2)
        sigma_in = torch.cat([sigmas[i] * s_in] * 2)
        cond_in = torch.cat([uncond, cond])

        image_conditioning = torch.cat([p.image_conditioning] * 2)
        cond_in = {"c_concat": [image_conditioning], "c_crossattn": [cond_in]}

        c_out, c_in = [K.utils.append_dims(k, x_in.ndim) for k in dnw.get_scalings(sigma_in)[skip:]]
        t = dnw.sigma_to_t(sigma_in)

        eps = shared.sd_model.apply_model(x_in * c_in, t, cond=cond_in)
        denoised_uncond, denoised_cond = (x_in + eps * c_out).chunk(2)

        denoised = denoised_uncond + (denoised_cond - denoised_uncond) * cfg_scale

        d = (x - denoised) / sigmas[i]
        dt = sigmas[i] - sigmas[i - 1]

        x = x + d * dt

        sd_samplers_common.store_latent(x)

        # This shouldn't be necessary, but solved some VRAM issues
        del x_in, sigma_in, cond_in, c_out, c_in, t,
        del eps, denoised_uncond, denoised_cond, denoised, d, dt

    shared.state.nextjob()

    return x / x.std()


Cached = namedtuple("Cached", ["noise", "cfg_scale", "steps", "latent", "original_prompt", "original_negative_prompt", "sigma_adjustment"])


# Based on changes suggested by briansemrau in https://github.com/AUTOMATIC1111/stable-diffusion-webui/issues/736
def find_noise_for_image_sigma_adjustment(p, cond, uncond, cfg_scale, steps):
    x = p.init_latent

    s_in = x.new_ones([x.shape[0]])
    if shared.sd_model.parameterization == "v":
        dnw = K.external.CompVisVDenoiser(shared.sd_model)
        skip = 1
    else:
        dnw = K.external.CompVisDenoiser(shared.sd_model)
        skip = 0
    sigmas = dnw.get_sigmas(steps).flip(0)

    shared.state.sampling_steps = steps

    for i in trange(1, len(sigmas)):
        shared.state.sampling_step += 1

        x_in = torch.cat([x] * 2)
        sigma_in = torch.cat([sigmas[i - 1] * s_in] * 2)
        cond_in = torch.cat([uncond, cond])

        image_conditioning = torch.cat([p.image_conditioning] * 2)
        cond_in = {"c_concat": [image_conditioning], "c_crossattn": [cond_in]}

        c_out, c_in = [K.utils.append_dims(k, x_in.ndim) for k in dnw.get_scalings(sigma_in)[skip:]]

        if i == 1:
            t = dnw.sigma_to_t(torch.cat([sigmas[i] * s_in] * 2))
        else:
            t = dnw.sigma_to_t(sigma_in)

        eps = shared.sd_model.apply_model(x_in * c_in, t, cond=cond_in)
        denoised_uncond, denoised_cond = (x_in + eps * c_out).chunk(2)

        denoised = denoised_uncond + (denoised_cond - denoised_uncond) * cfg_scale

        if i == 1:
            d = (x - denoised) / (2 * sigmas[i])
        else:
            d = (x - denoised) / sigmas[i - 1]

        dt = sigmas[i] - sigmas[i - 1]
        x = x + d * dt

        sd_samplers_common.store_latent(x)

        # This shouldn't be necessary, but solved some VRAM issues
        del x_in, sigma_in, cond_in, c_out, c_in, t,
        del eps, denoised_uncond, denoised_cond, denoised, d, dt

    shared.state.nextjob()

    return x / sigmas[-1]


class Script(scripts.Script):
    def __init__(self):
        self.cache = None

    def title(self):
        return "img2img alternative test"

    def show(self, is_img2img):
        return is_img2img

    def ui(self, is_img2img):
        info = gr.Markdown('''
        * `CFG Scale` should be 2 or lower.
        ''')

        override_sampler = gr.Checkbox(label="Override `Sampling method` to Euler?(this method is built for it)", value=True, elem_id=self.elem_id("override_sampler"))

        override_prompt = gr.Checkbox(label="Override `prompt` to the same value as `original prompt`?(and `negative prompt`)", value=True, elem_id=self.elem_id("override_prompt"))
        original_prompt = gr.Textbox(label="Original prompt", lines=1, elem_id=self.elem_id("original_prompt"))
        original_negative_prompt = gr.Textbox(label="Original negative prompt", lines=1, elem_id=self.elem_id("original_negative_prompt"))

        override_steps = gr.Checkbox(label="Override `Sampling Steps` to the same value as `Decode steps`?", value=True, elem_id=self.elem_id("override_steps"))
        st = gr.Slider(label="Decode steps", minimum=1, maximum=150, step=1, value=50, elem_id=self.elem_id("st"))

        override_strength = gr.Checkbox(label="Override `Denoising strength` to 1?", value=True, elem_id=self.elem_id("override_strength"))

        cfg = gr.Slider(label="Decode CFG scale", minimum=0.0, maximum=15.0, step=0.1, value=1.0, elem_id=self.elem_id("cfg"))
        randomness = gr.Slider(label="Randomness", minimum=0.0, maximum=1.0, step=0.01, value=0.0, elem_id=self.elem_id("randomness"))
        sigma_adjustment = gr.Checkbox(label="Sigma adjustment for finding noise for image", value=False, elem_id=self.elem_id("sigma_adjustment"))

        return [
            info,
            override_sampler,
            override_prompt, original_prompt, original_negative_prompt,
            override_steps, st,
            override_strength,
            cfg, randomness, sigma_adjustment,
        ]

    def run(self, p, _, override_sampler, override_prompt, original_prompt, original_negative_prompt, override_steps, st, override_strength, cfg, randomness, sigma_adjustment):
        # Override
        if override_sampler:
            p.sampler_name = "Euler"
        if override_prompt:
            p.prompt = original_prompt
            p.negative_prompt = original_negative_prompt
        if override_steps:
            p.steps = st
        if override_strength:
            p.denoising_strength = 1.0

        def sample_extra(conditioning, unconditional_conditioning, seeds, subseeds, subseed_strength, prompts):
            lat = (p.init_latent.cpu().numpy() * 10).astype(int)

            same_params = self.cache is not None and self.cache.cfg_scale == cfg and self.cache.steps == st \
                                and self.cache.original_prompt == original_prompt \
                                and self.cache.original_negative_prompt == original_negative_prompt \
                                and self.cache.sigma_adjustment == sigma_adjustment
            same_everything = same_params and self.cache.latent.shape == lat.shape and np.abs(self.cache.latent-lat).sum() < 100

            if same_everything:
                rec_noise = self.cache.noise
            else:
                shared.state.job_count += 1
                cond = p.sd_model.get_learned_conditioning(p.batch_size * [original_prompt])
                uncond = p.sd_model.get_learned_conditioning(p.batch_size * [original_negative_prompt])
                if sigma_adjustment:
                    rec_noise = find_noise_for_image_sigma_adjustment(p, cond, uncond, cfg, st)
                else:
                    rec_noise = find_noise_for_image(p, cond, uncond, cfg, st)
                self.cache = Cached(rec_noise, cfg, st, lat, original_prompt, original_negative_prompt, sigma_adjustment)

            rand_noise = processing.create_random_tensors(p.init_latent.shape[1:], seeds=seeds, subseeds=subseeds, subseed_strength=p.subseed_strength, seed_resize_from_h=p.seed_resize_from_h, seed_resize_from_w=p.seed_resize_from_w, p=p)

            combined_noise = ((1 - randomness) * rec_noise + randomness * rand_noise) / ((randomness**2 + (1-randomness)**2) ** 0.5)

            sampler = sd_samplers.create_sampler(p.sampler_name, p.sd_model)

            sigmas = sampler.model_wrap.get_sigmas(p.steps)

            noise_dt = combined_noise - (p.init_latent / sigmas[0])

            p.seed = p.seed + 1

            return sampler.sample_img2img(p, p.init_latent, noise_dt, conditioning, unconditional_conditioning, image_conditioning=p.image_conditioning)

        p.sample = sample_extra

        p.extra_generation_params["Decode prompt"] = original_prompt
        p.extra_generation_params["Decode negative prompt"] = original_negative_prompt
        p.extra_generation_params["Decode CFG scale"] = cfg
        p.extra_generation_params["Decode steps"] = st
        p.extra_generation_params["Randomness"] = randomness
        p.extra_generation_params["Sigma Adjustment"] = sigma_adjustment

        processed = processing.process_images(p)

        return processed
)
)

initialize.check_versions(pip install torch)
from collections import namedtuple

import numpy as np
from tqdm import trange

import modules.scripts as scripts
import gradio as gr

from modules import processing, shared, sd_samplers, sd_samplers_common

import torch
import k_diffusion as K

def find_noise_for_image(p, cond, uncond, cfg_scale, steps):
    x = p.init_latent

    s_in = x.new_ones([x.shape[0]])
    if shared.sd_model.parameterization == "v":
        dnw = K.external.CompVisVDenoiser(shared.sd_model)
        skip = 1
    else:
        dnw = K.external.CompVisDenoiser(shared.sd_model)
        skip = 0
    sigmas = dnw.get_sigmas(steps).flip(0)

    shared.state.sampling_steps = steps

    for i in trange(1, len(sigmas)):
        shared.state.sampling_step += 1

        x_in = torch.cat([x] * 2)
        sigma_in = torch.cat([sigmas[i] * s_in] * 2)
        cond_in = torch.cat([uncond, cond])

        image_conditioning = torch.cat([p.image_conditioning] * 2)
        cond_in = {"c_concat": [image_conditioning], "c_crossattn": [cond_in]}

        c_out, c_in = [K.utils.append_dims(k, x_in.ndim) for k in dnw.get_scalings(sigma_in)[skip:]]
        t = dnw.sigma_to_t(sigma_in)

        eps = shared.sd_model.apply_model(x_in * c_in, t, cond=cond_in)
        denoised_uncond, denoised_cond = (x_in + eps * c_out).chunk(2)

        denoised = denoised_uncond + (denoised_cond - denoised_uncond) * cfg_scale

        d = (x - denoised) / sigmas[i]
        dt = sigmas[i] - sigmas[i - 1]

        x = x + d * dt

        sd_samplers_common.store_latent(x)

        # This shouldn't be necessary, but solved some VRAM issues
        del x_in, sigma_in, cond_in, c_out, c_in, t,
        del eps, denoised_uncond, denoised_cond, denoised, d, dt

    shared.state.nextjob()

    return x / x.std()


Cached = namedtuple("Cached", ["noise", "cfg_scale", "steps", "latent", "original_prompt", "original_negative_prompt", "sigma_adjustment"])


# Based on changes suggested by briansemrau in https://github.com/AUTOMATIC1111/stable-diffusion-webui/issues/736
def find_noise_for_image_sigma_adjustment(p, cond, uncond, cfg_scale, steps):
    x = p.init_latent

    s_in = x.new_ones([x.shape[0]])
    if shared.sd_model.parameterization == "v":
        dnw = K.external.CompVisVDenoiser(shared.sd_model)
        skip = 1
    else:
        dnw = K.external.CompVisDenoiser(shared.sd_model)
        skip = 0
    sigmas = dnw.get_sigmas(steps).flip(0)

    shared.state.sampling_steps = steps

    for i in trange(1, len(sigmas)):
        shared.state.sampling_step += 1

        x_in = torch.cat([x] * 2)
        sigma_in = torch.cat([sigmas[i - 1] * s_in] * 2)
        cond_in = torch.cat([uncond, cond])

        image_conditioning = torch.cat([p.image_conditioning] * 2)
        cond_in = {"c_concat": [image_conditioning], "c_crossattn": [cond_in]}

        c_out, c_in = [K.utils.append_dims(k, x_in.ndim) for k in dnw.get_scalings(sigma_in)[skip:]]

        if i == 1:
            t = dnw.sigma_to_t(torch.cat([sigmas[i] * s_in] * 2))
        else:
            t = dnw.sigma_to_t(sigma_in)

        eps = shared.sd_model.apply_model(x_in * c_in, t, cond=cond_in)
        denoised_uncond, denoised_cond = (x_in + eps * c_out).chunk(2)

        denoised = denoised_uncond + (denoised_cond - denoised_uncond) * cfg_scale

        if i == 1:
            d = (x - denoised) / (2 * sigmas[i])
        else:
            d = (x - denoised) / sigmas[i - 1]

        dt = sigmas[i] - sigmas[i - 1]
        x = x + d * dt

        sd_samplers_common.store_latent(x)

        # This shouldn't be necessary, but solved some VRAM issues
        del x_in, sigma_in, cond_in, c_out, c_in, t,
        del eps, denoised_uncond, denoised_cond, denoised, d, dt

    shared.state.nextjob()

    return x / sigmas[-1]


class Script(scripts.Script):
    def __init__(self):
        self.cache = None

    def title(self):
        return "img2img alternative test"

    def show(self, is_img2img):
        return is_img2img

    def ui(self, is_img2img):
        info = gr.Markdown('''
        * `CFG Scale` should be 2 or lower.
        ''')

        override_sampler = gr.Checkbox(label="Override `Sampling method` to Euler?(this method is built for it)", value=True, elem_id=self.elem_id("override_sampler"))

        override_prompt = gr.Checkbox(label="Override `prompt` to the same value as `original prompt`?(and `negative prompt`)", value=True, elem_id=self.elem_id("override_prompt"))
        original_prompt = gr.Textbox(label="Original prompt", lines=1, elem_id=self.elem_id("original_prompt"))
        original_negative_prompt = gr.Textbox(label="Original negative prompt", lines=1, elem_id=self.elem_id("original_negative_prompt"))

        override_steps = gr.Checkbox(label="Override `Sampling Steps` to the same value as `Decode steps`?", value=True, elem_id=self.elem_id("override_steps"))
        st = gr.Slider(label="Decode steps", minimum=1, maximum=150, step=1, value=50, elem_id=self.elem_id("st"))

        override_strength = gr.Checkbox(label="Override `Denoising strength` to 1?", value=True, elem_id=self.elem_id("override_strength"))

        cfg = gr.Slider(label="Decode CFG scale", minimum=0.0, maximum=15.0, step=0.1, value=1.0, elem_id=self.elem_id("cfg"))
        randomness = gr.Slider(label="Randomness", minimum=0.0, maximum=1.0, step=0.01, value=0.0, elem_id=self.elem_id("randomness"))
        sigma_adjustment = gr.Checkbox(label="Sigma adjustment for finding noise for image", value=False, elem_id=self.elem_id("sigma_adjustment"))

        return [
            info,
            override_sampler,
            override_prompt, original_prompt, original_negative_prompt,
            override_steps, st,
            override_strength,
            cfg, randomness, sigma_adjustment,
        ]

    def run(self, p, _, override_sampler, override_prompt, original_prompt, original_negative_prompt, override_steps, st, override_strength, cfg, randomness, sigma_adjustment):
        # Override
        if override_sampler:
            p.sampler_name = "Euler"
        if override_prompt:
            p.prompt = original_prompt
            p.negative_prompt = original_negative_prompt
        if override_steps:
            p.steps = st
        if override_strength:
            p.denoising_strength = 1.0

        def sample_extra(conditioning, unconditional_conditioning, seeds, subseeds, subseed_strength, prompts):
            lat = (p.init_latent.cpu().numpy() * 10).astype(int)

            same_params = self.cache is not None and self.cache.cfg_scale == cfg and self.cache.steps == st \
                                and self.cache.original_prompt == original_prompt \
                                and self.cache.original_negative_prompt == original_negative_prompt \
                                and self.cache.sigma_adjustment == sigma_adjustment
            same_everything = same_params and self.cache.latent.shape == lat.shape and np.abs(self.cache.latent-lat).sum() < 100

            if same_everything:
                rec_noise = self.cache.noise
            else:
                shared.state.job_count += 1
                cond = p.sd_model.get_learned_conditioning(p.batch_size * [original_prompt])
                uncond = p.sd_model.get_learned_conditioning(p.batch_size * [original_negative_prompt])
                if sigma_adjustment:
                    rec_noise = find_noise_for_image_sigma_adjustment(p, cond, uncond, cfg, st)
                else:
                    rec_noise = find_noise_for_image(p, cond, uncond, cfg, st)
                self.cache = Cached(rec_noise, cfg, st, lat, original_prompt, original_negative_prompt, sigma_adjustment)

            rand_noise = processing.create_random_tensors(p.init_latent.shape[1:], seeds=seeds, subseeds=subseeds, subseed_strength=p.subseed_strength, seed_resize_from_h=p.seed_resize_from_h, seed_resize_from_w=p.seed_resize_from_w, p=p)

            combined_noise = ((1 - randomness) * rec_noise + randomness * rand_noise) / ((randomness**2 + (1-randomness)**2) ** 0.5)

            sampler = sd_samplers.create_sampler(p.sampler_name, p.sd_model)

            sigmas = sampler.model_wrap.get_sigmas(p.steps)

            noise_dt = combined_noise - (p.init_latent / sigmas[0])

            p.seed = p.seed + 1

            return sampler.sample_img2img(p, p.init_latent, noise_dt, conditioning, unconditional_conditioning, image_conditioning=p.image_conditioning)

        p.sample = sample_extra

        p.extra_generation_params["Decode prompt"] = original_prompt
        p.extra_generation_params["Decode negative prompt"] = original_negative_prompt
        p.extra_generation_params["Decode CFG scale"] = cfg
        p.extra_generation_params["Decode steps"] = st
        p.extra_generation_params["Randomness"] = randomness
        p.extra_generation_params["Sigma Adjustment"] = sigma_adjustment

        processed = processing.process_images(p)

        return processed
from collections import namedtuple

import numpy as np
from tqdm import trange

import modules.scripts as scripts
import gradio as gr

from modules import processing, shared, sd_samplers, sd_samplers_common

import torch
import k_diffusion as K

def find_noise_for_image(p, cond, uncond, cfg_scale, steps):
    x = p.init_latent

    s_in = x.new_ones([x.shape[0]])
    if shared.sd_model.parameterization == "v":
        dnw = K.external.CompVisVDenoiser(shared.sd_model)
        skip = 1
    else:
        dnw = K.external.CompVisDenoiser(shared.sd_model)
        skip = 0
    sigmas = dnw.get_sigmas(steps).flip(0)

    shared.state.sampling_steps = steps

    for i in trange(1, len(sigmas)):
        shared.state.sampling_step += 1

        x_in = torch.cat([x] * 2)
        sigma_in = torch.cat([sigmas[i] * s_in] * 2)
        cond_in = torch.cat([uncond, cond])

        image_conditioning = torch.cat([p.image_conditioning] * 2)
        cond_in = {"c_concat": [image_conditioning], "c_crossattn": [cond_in]}

        c_out, c_in = [K.utils.append_dims(k, x_in.ndim) for k in dnw.get_scalings(sigma_in)[skip:]]
        t = dnw.sigma_to_t(sigma_in)

        eps = shared.sd_model.apply_model(x_in * c_in, t, cond=cond_in)
        denoised_uncond, denoised_cond = (x_in + eps * c_out).chunk(2)

        denoised = denoised_uncond + (denoised_cond - denoised_uncond) * cfg_scale

        d = (x - denoised) / sigmas[i]
        dt = sigmas[i] - sigmas[i - 1]

        x = x + d * dt

        sd_samplers_common.store_latent(x)

        # This shouldn't be necessary, but solved some VRAM issues
        del x_in, sigma_in, cond_in, c_out, c_in, t,
        del eps, denoised_uncond, denoised_cond, denoised, d, dt

    shared.state.nextjob()

    return x / x.std()


Cached = namedtuple("Cached", ["noise", "cfg_scale", "steps", "latent", "original_prompt", "original_negative_prompt", "sigma_adjustment"])


# Based on changes suggested by briansemrau in https://github.com/AUTOMATIC1111/stable-diffusion-webui/issues/736
def find_noise_for_image_sigma_adjustment(p, cond, uncond, cfg_scale, steps):
    x = p.init_latent

    s_in = x.new_ones([x.shape[0]])
    if shared.sd_model.parameterization == "v":
        dnw = K.external.CompVisVDenoiser(shared.sd_model)
        skip = 1
    else:
        dnw = K.external.CompVisDenoiser(shared.sd_model)
        skip = 0
    sigmas = dnw.get_sigmas(steps).flip(0)

    shared.state.sampling_steps = steps

    for i in trange(1, len(sigmas)):
        shared.state.sampling_step += 1

        x_in = torch.cat([x] * 2)
        sigma_in = torch.cat([sigmas[i - 1] * s_in] * 2)
        cond_in = torch.cat([uncond, cond])

        image_conditioning = torch.cat([p.image_conditioning] * 2)
        cond_in = {"c_concat": [image_conditioning], "c_crossattn": [cond_in]}

        c_out, c_in = [K.utils.append_dims(k, x_in.ndim) for k in dnw.get_scalings(sigma_in)[skip:]]

        if i == 1:
            t = dnw.sigma_to_t(torch.cat([sigmas[i] * s_in] * 2))
        else:
            t = dnw.sigma_to_t(sigma_in)

        eps = shared.sd_model.apply_model(x_in * c_in, t, cond=cond_in)
        denoised_uncond, denoised_cond = (x_in + eps * c_out).chunk(2)

        denoised = denoised_uncond + (denoised_cond - denoised_uncond) * cfg_scale

        if i == 1:
            d = (x - denoised) / (2 * sigmas[i])
        else:
            d = (x - denoised) / sigmas[i - 1]

        dt = sigmas[i] - sigmas[i - 1]
        x = x + d * dt

        sd_samplers_common.store_latent(x)

        # This shouldn't be necessary, but solved some VRAM issues
        del x_in, sigma_in, cond_in, c_out, c_in, t,
        del eps, denoised_uncond, denoised_cond, denoised, d, dt

    shared.state.nextjob()

    return x / sigmas[-1]


class Script(scripts.Script):
    def __init__(self):
        self.cache = None

    def title(self):
        return "img2img alternative test"

    def show(self, is_img2img):
        return is_img2img

    def ui(self, is_img2img):
        info = gr.Markdown('''
        * `CFG Scale` should be 2 or lower.
        ''')

        override_sampler = gr.Checkbox(label="Override `Sampling method` to Euler?(this method is built for it)", value=True, elem_id=self.elem_id("override_sampler"))

        override_prompt = gr.Checkbox(label="Override `prompt` to the same value as `original prompt`?(and `negative prompt`)", value=True, elem_id=self.elem_id("override_prompt"))
        original_prompt = gr.Textbox(label="Original prompt", lines=1, elem_id=self.elem_id("original_prompt"))
        original_negative_prompt = gr.Textbox(label="Original negative prompt", lines=1, elem_id=self.elem_id("original_negative_prompt"))

        override_steps = gr.Checkbox(label="Override `Sampling Steps` to the same value as `Decode steps`?", value=True, elem_id=self.elem_id("override_steps"))
        st = gr.Slider(label="Decode steps", minimum=1, maximum=150, step=1, value=50, elem_id=self.elem_id("st"))

        override_strength = gr.Checkbox(label="Override `Denoising strength` to 1?", value=True, elem_id=self.elem_id("override_strength"))

        cfg = gr.Slider(label="Decode CFG scale", minimum=0.0, maximum=15.0, step=0.1, value=1.0, elem_id=self.elem_id("cfg"))
        randomness = gr.Slider(label="Randomness", minimum=0.0, maximum=1.0, step=0.01, value=0.0, elem_id=self.elem_id("randomness"))
        sigma_adjustment = gr.Checkbox(label="Sigma adjustment for finding noise for image", value=False, elem_id=self.elem_id("sigma_adjustment"))

        return [
            info,
            override_sampler,
            override_prompt, original_prompt, original_negative_prompt,
            override_steps, st,
            override_strength,
            cfg, randomness, sigma_adjustment,
        ]

    def run(self, p, _, override_sampler, override_prompt, original_prompt, original_negative_prompt, override_steps, st, override_strength, cfg, randomness, sigma_adjustment):
        # Override
        if override_sampler:
            p.sampler_name = "Euler"
        if override_prompt:
            p.prompt = original_prompt
            p.negative_prompt = original_negative_prompt
        if override_steps:
            p.steps = st
        if override_strength:
            p.denoising_strength = 1.0

        def sample_extra(conditioning, unconditional_conditioning, seeds, subseeds, subseed_strength, prompts):
            lat = (p.init_latent.cpu().numpy() * 10).astype(int)

            same_params = self.cache is not None and self.cache.cfg_scale == cfg and self.cache.steps == st \
                                and self.cache.original_prompt == original_prompt \
                                and self.cache.original_negative_prompt == original_negative_prompt \
                                and self.cache.sigma_adjustment == sigma_adjustment
            same_everything = same_params and self.cache.latent.shape == lat.shape and np.abs(self.cache.latent-lat).sum() < 100

            if same_everything:
                rec_noise = self.cache.noise
            else:
                shared.state.job_count += 1
                cond = p.sd_model.get_learned_conditioning(p.batch_size * [original_prompt])
                uncond = p.sd_model.get_learned_conditioning(p.batch_size * [original_negative_prompt])
                if sigma_adjustment:
                    rec_noise = find_noise_for_image_sigma_adjustment(p, cond, uncond, cfg, st)
                else:
                    rec_noise = find_noise_for_image(p, cond, uncond, cfg, st)
                self.cache = Cached(rec_noise, cfg, st, lat, original_prompt, original_negative_prompt, sigma_adjustment)

            rand_noise = processing.create_random_tensors(p.init_latent.shape[1:], seeds=seeds, subseeds=subseeds, subseed_strength=p.subseed_strength, seed_resize_from_h=p.seed_resize_from_h, seed_resize_from_w=p.seed_resize_from_w, p=p)

            combined_noise = ((1 - randomness) * rec_noise + randomness * rand_noise) / ((randomness**2 + (1-randomness)**2) ** 0.5)

            sampler = sd_samplers.create_sampler(p.sampler_name, p.sd_model)

            sigmas = sampler.model_wrap.get_sigmas(p.steps)

            noise_dt = combined_noise - (p.init_latent / sigmas[0])

            p.seed = p.seed + 1

            return sampler.sample_img2img(p, p.init_latent, noise_dt, conditioning, unconditional_conditioning, image_conditioning=p.image_conditioning)

        p.sample = sample_extra

        p.extra_generation_params["Decode prompt"] = original_prompt
        p.extra_generation_params["Decode negative prompt"] = original_negative_prompt
        p.extra_generation_params["Decode CFG scale"] = cfg
        p.extra_generation_params["Decode steps"] = st
        p.extra_generation_params["Randomness"] = randomness
        p.extra_generation_params["Sigma Adjustment"] = sigma_adjustment

        processed = processing.process_images(p)

        return processed
from collections import namedtuple

import numpy as np
from tqdm import trange

import modules.scripts as scripts
import gradio as gr

from modules import processing, shared, sd_samplers, sd_samplers_common

import torch
import k_diffusion as K

def find_noise_for_image(p, cond, uncond, cfg_scale, steps):
    x = p.init_latent

    s_in = x.new_ones([x.shape[0]])
    if shared.sd_model.parameterization == "v":
        dnw = K.external.CompVisVDenoiser(shared.sd_model)
        skip = 1
    else:
        dnw = K.external.CompVisDenoiser(shared.sd_model)
        skip = 0
    sigmas = dnw.get_sigmas(steps).flip(0)

    shared.state.sampling_steps = steps

    for i in trange(1, len(sigmas)):
        shared.state.sampling_step += 1

        x_in = torch.cat([x] * 2)
        sigma_in = torch.cat([sigmas[i] * s_in] * 2)
        cond_in = torch.cat([uncond, cond])

        image_conditioning = torch.cat([p.image_conditioning] * 2)
        cond_in = {"c_concat": [image_conditioning], "c_crossattn": [cond_in]}

        c_out, c_in = [K.utils.append_dims(k, x_in.ndim) for k in dnw.get_scalings(sigma_in)[skip:]]
        t = dnw.sigma_to_t(sigma_in)

        eps = shared.sd_model.apply_model(x_in * c_in, t, cond=cond_in)
        denoised_uncond, denoised_cond = (x_in + eps * c_out).chunk(2)

        denoised = denoised_uncond + (denoised_cond - denoised_uncond) * cfg_scale

        d = (x - denoised) / sigmas[i]
        dt = sigmas[i] - sigmas[i - 1]

        x = x + d * dt

        sd_samplers_common.store_latent(x)

        # This shouldn't be necessary, but solved some VRAM issues
        del x_in, sigma_in, cond_in, c_out, c_in, t,
        del eps, denoised_uncond, denoised_cond, denoised, d, dt

    shared.state.nextjob()

    return x / x.std()


Cached = namedtuple("Cached", ["noise", "cfg_scale", "steps", "latent", "original_prompt", "original_negative_prompt", "sigma_adjustment"])


# Based on changes suggested by briansemrau in https://github.com/AUTOMATIC1111/stable-diffusion-webui/issues/736
def find_noise_for_image_sigma_adjustment(p, cond, uncond, cfg_scale, steps):
    x = p.init_latent

    s_in = x.new_ones([x.shape[0]])
    if shared.sd_model.parameterization == "v":
        dnw = K.external.CompVisVDenoiser(shared.sd_model)
        skip = 1
    else:
        dnw = K.external.CompVisDenoiser(shared.sd_model)
        skip = 0
    sigmas = dnw.get_sigmas(steps).flip(0)

    shared.state.sampling_steps = steps

    for i in trange(1, len(sigmas)):
        shared.state.sampling_step += 1

        x_in = torch.cat([x] * 2)
        sigma_in = torch.cat([sigmas[i - 1] * s_in] * 2)
        cond_in = torch.cat([uncond, cond])

        image_conditioning = torch.cat([p.image_conditioning] * 2)
        cond_in = {"c_concat": [image_conditioning], "c_crossattn": [cond_in]}

        c_out, c_in = [K.utils.append_dims(k, x_in.ndim) for k in dnw.get_scalings(sigma_in)[skip:]]

        if i == 1:
            t = dnw.sigma_to_t(torch.cat([sigmas[i] * s_in] * 2))
        else:
            t = dnw.sigma_to_t(sigma_in)

        eps = shared.sd_model.apply_model(x_in * c_in, t, cond=cond_in)
        denoised_uncond, denoised_cond = (x_in + eps * c_out).chunk(2)

        denoised = denoised_uncond + (denoised_cond - denoised_uncond) * cfg_scale

        if i == 1:
            d = (x - denoised) / (2 * sigmas[i])
        else:
            d = (x - denoised) / sigmas[i - 1]

        dt = sigmas[i] - sigmas[i - 1]
        x = x + d * dt

        sd_samplers_common.store_latent(x)

        # This shouldn't be necessary, but solved some VRAM issues
        del x_in, sigma_in, cond_in, c_out, c_in, t,
        del eps, denoised_uncond, denoised_cond, denoised, d, dt

    shared.state.nextjob()

    return x / sigmas[-1]


class Script(scripts.Script):
    def __init__(self):
        self.cache = None

    def title(self):
        return "img2img alternative test"

    def show(self, is_img2img):
        return is_img2img

    def ui(self, is_img2img):
        info = gr.Markdown('''
        * `CFG Scale` should be 2 or lower.
        ''')

        override_sampler = gr.Checkbox(label="Override `Sampling method` to Euler?(this method is built for it)", value=True, elem_id=self.elem_id("override_sampler"))

        override_prompt = gr.Checkbox(label="Override `prompt` to the same value as `original prompt`?(and `negative prompt`)", value=True, elem_id=self.elem_id("override_prompt"))
        original_prompt = gr.Textbox(label="Original prompt", lines=1, elem_id=self.elem_id("original_prompt"))
        original_negative_prompt = gr.Textbox(label="Original negative prompt", lines=1, elem_id=self.elem_id("original_negative_prompt"))

        override_steps = gr.Checkbox(label="Override `Sampling Steps` to the same value as `Decode steps`?", value=True, elem_id=self.elem_id("override_steps"))
        st = gr.Slider(label="Decode steps", minimum=1, maximum=150, step=1, value=50, elem_id=self.elem_id("st"))

        override_strength = gr.Checkbox(label="Override `Denoising strength` to 1?", value=True, elem_id=self.elem_id("override_strength"))

        cfg = gr.Slider(label="Decode CFG scale", minimum=0.0, maximum=15.0, step=0.1, value=1.0, elem_id=self.elem_id("cfg"))
        randomness = gr.Slider(label="Randomness", minimum=0.0, maximum=1.0, step=0.01, value=0.0, elem_id=self.elem_id("randomness"))
        sigma_adjustment = gr.Checkbox(label="Sigma adjustment for finding noise for image", value=False, elem_id=self.elem_id("sigma_adjustment"))

        return [
            info,
            override_sampler,
            override_prompt, original_prompt, original_negative_prompt,
            override_steps, st,
            override_strength,
            cfg, randomness, sigma_adjustment,
        ]

    def run(self, p, _, override_sampler, override_prompt, original_prompt, original_negative_prompt, override_steps, st, override_strength, cfg, randomness, sigma_adjustment):
        # Override
        if override_sampler:
            p.sampler_name = "Euler"
        if override_prompt:
            p.prompt = original_prompt
            p.negative_prompt = original_negative_prompt
        if override_steps:
            p.steps = st
        if override_strength:
            p.denoising_strength = 1.0

        def sample_extra(conditioning, unconditional_conditioning, seeds, subseeds, subseed_strength, prompts):
            lat = (p.init_latent.cpu().numpy() * 10).astype(int)

            same_params = self.cache is not None and self.cache.cfg_scale == cfg and self.cache.steps == st \
                                and self.cache.original_prompt == original_prompt \
                                and self.cache.original_negative_prompt == original_negative_prompt \
                                and self.cache.sigma_adjustment == sigma_adjustment
            same_everything = same_params and self.cache.latent.shape == lat.shape and np.abs(self.cache.latent-lat).sum() < 100

            if same_everything:
                rec_noise = self.cache.noise
            else:
                shared.state.job_count += 1
                cond = p.sd_model.get_learned_conditioning(p.batch_size * [original_prompt])
                uncond = p.sd_model.get_learned_conditioning(p.batch_size * [original_negative_prompt])
                if sigma_adjustment:
                    rec_noise = find_noise_for_image_sigma_adjustment(p, cond, uncond, cfg, st)
                else:
                    rec_noise = find_noise_for_image(p, cond, uncond, cfg, st)
                self.cache = Cached(rec_noise, cfg, st, lat, original_prompt, original_negative_prompt, sigma_adjustment)

            rand_noise = processing.create_random_tensors(p.init_latent.shape[1:], seeds=seeds, subseeds=subseeds, subseed_strength=p.subseed_strength, seed_resize_from_h=p.seed_resize_from_h, seed_resize_from_w=p.seed_resize_from_w, p=p)

            combined_noise = ((1 - randomness) * rec_noise + randomness * rand_noise) / ((randomness**2 + (1-randomness)**2) ** 0.5)

            sampler = sd_samplers.create_sampler(p.sampler_name, p.sd_model)

            sigmas = sampler.model_wrap.get_sigmas(p.steps)

            noise_dt = combined_noise - (p.init_latent / sigmas[0])

            p.seed = p.seed + 1

            return sampler.sample_img2img(p, p.init_latent, noise_dt, conditioning, unconditional_conditioning, image_conditioning=p.image_conditioning)

        p.sample = sample_extra

        p.extra_generation_params["Decode prompt"] = original_prompt
        p.extra_generation_params["Decode negative prompt"] = original_negative_prompt
        p.extra_generation_params["Decode CFG scale"] = cfg
        p.extra_generation_params["Decode steps"] = st
        p.extra_generation_params["Randomness"] = randomness
        p.extra_generation_params["Sigma Adjustment"] = sigma_adjustment

        processed = processing.process_images(p)

        return processed


def create_api(app):
    from modules.api.api import Api
    from modules.call_queue import queue_lock

    api = Api(app, queue_lock)
    return api


def api_only():
    from fastapi import FastAPI
    from modules.shared_cmd_options import cmd_opts

    initialize.initialize()

    app = FastAPI()
    initialize_util.setup_middleware(app)
    api = create_api(app)

    from modules import script_callbacks
    script_callbacks.before_ui_callback()
    script_callbacks.app_started_callback(None, app)

    print(f"Startup time: {startup_timer.summary()}.")
    api.launch(
        server_name=initialize_util.gradio_server_name(),
        port=cmd_opts.port if cmd_opts.port else 7861,
        root_path=f"/{cmd_opts.subpath}" if cmd_opts.subpath else ""
    )


def warning_if_invalid_install_dir():
    """
    Shows a warning if the webui is installed under a path that contains a leading dot in any of its parent directories.

    Gradio '/file=' route will block access to files that have a leading dot in the path segments.
    We use this route to serve files such as JavaScript and CSS to the webpage,
    if those files are blocked, the webpage will not function properly.
    See https://github.com/AUTOMATIC1111/stable-diffusion-webui/issues/13292

    This is a security feature was added to Gradio 3.32.0 and is removed in later versions,
    this function replicates Gradio file access blocking logic.

    This check should be removed when it's no longer applicable.
    """
    from packaging.version import parse
    from pathlib import Path
    import gradio

    if parse('3.32.0') <= parse(gradio.__version__) < parse('4'):

        def abspath(path):
            """modified from Gradio 3.41.2 gradio.utils.abspath()"""
            if path.is_absolute():
                return path
            is_symlink = path.is_symlink() or any(parent.is_symlink() for parent in path.parents)
            return Path.cwd() / path if (is_symlink or path == path.resolve()) else path.resolve()

        webui_root = Path(__file__).parent
        if any(part.startswith(".") for part in abspath(webui_root).parts):
            print(f'''{"!"*25} Warning {"!"*25}
WebUI is installed in a directory that has a leading dot (.) in one of its parent directories.
This will prevent WebUI from functioning properly.
Please move the installation to a different directory.
Current path: "{webui_root}"
For more information see: https://github.com/AUTOMATIC1111/stable-diffusion-webui/issues/13292
{"!"*25} Warning {"!"*25}''')


def webui():
    from modules.shared_cmd_options import cmd_opts

    launch_api = cmd_opts.api
    initialize.initialize()

    from modules import shared, ui_tempdir, script_callbacks, ui, progress, ui_extra_networks

    warning_if_invalid_install_dir()

    while 1:
        if shared.opts.clean_temp_dir_at_start:
            ui_tempdir.cleanup_tmpdr()
            startup_timer.record("cleanup temp dir")

        script_callbacks.before_ui_callback()
        startup_timer.record("scripts before_ui_callback")

        shared.demo = ui.create_ui()
        startup_timer.record("create ui")

        if not cmd_opts.no_gradio_queue:
            shared.demo.queue(64)

        gradio_auth_creds = list(initialize_util.get_gradio_auth_creds()) or None

        auto_launch_browser = False
        if os.getenv('SD_WEBUI_RESTARTING') != '1':
            if shared.opts.auto_launch_browser == "Remote" or cmd_opts.autolaunch:
                auto_launch_browser = True
            elif shared.opts.auto_launch_browser == "Local":
                auto_launch_browser = not cmd_opts.webui_is_non_local

        app, local_url, share_url = shared.demo.launch(
            share=cmd_opts.share,
            server_name=initialize_util.gradio_server_name(),
            server_port=cmd_opts.port,
            ssl_keyfile=cmd_opts.tls_keyfile,
            ssl_certfile=cmd_opts.tls_certfile,
            ssl_verify=cmd_opts.disable_tls_verify,
            debug=cmd_opts.gradio_debug,
            auth=gradio_auth_creds,
            inbrowser=auto_launch_browser,
            prevent_thread_lock=True,
            allowed_paths=cmd_opts.gradio_allowed_path,
            app_kwargs={
                "docs_url": "/docs",
                "redoc_url": "/redoc",
            },
            root_path=f"/{cmd_opts.subpath}" if cmd_opts.subpath else "",
        )

        startup_timer.record("gradio launch")

        # gradio uses a very open CORS policy via app.user_middleware, which makes it possible for
        # an attacker to trick the user into opening a malicious HTML page, which makes a request to the
        # running web ui and do whatever the attacker wants, including installing an extension and
        # running its code. We disable this here. Suggested by RyotaK.
        app.user_middleware = [x for x in app.user_middleware if x.cls.__name__ != 'CORSMiddleware']

        initialize_util.setup_middleware(app)

        progress.setup_progress_api(app)
        ui.setup_ui_api(app)

        if launch_api:
            create_api(app)

        ui_extra_networks.add_pages_to_demo(app)

        startup_timer.record("add APIs")

        with startup_timer.subcategory("app_started_callback"):
            script_callbacks.app_started_callback(shared.demo, app)

        timer.startup_record = startup_timer.dump()
        print(f"Startup time: {startup_timer.summary()}.")

        try:
            while True:
                server_command = shared.state.wait_for_server_command(timeout=5)
                if server_command:
                    if server_command in ("stop", "restart"):
                        break
                    else:
                        print(f"Unknown server command: {server_command}")
        except KeyboardInterrupt:
            print('Caught KeyboardInterrupt, stopping...')
            server_command = "stop"

        if server_command == "stop":
            print("Stopping server...")
            # If we catch a keyboard interrupt, we want to stop the server and exit.
            shared.demo.close()
            break

        # disable auto launch webui in browser for subsequent UI Reload
        os.environ.setdefault('SD_WEBUI_RESTARTING', '1')

        print('Restarting UI...')
        shared.demo.close()
        time.sleep(0.5)
        startup_timer.reset()
        script_callbacks.app_reload_callback()
        startup_timer.record("app reload callback")
        script_callbacks.script_unloaded_callback()
        startup_timer.record("scripts unloaded callback")
        initialize.initialize_rest(reload_script_modules=True)


if __name__ == "__main__":
    from modules.shared_cmd_options import cmd_opts

    if cmd_opts.nowebui:
        api_only()
    else:
        webui()
