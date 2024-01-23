import torch
import torch.optim as optim

from PIL import Image
import matplotlib.pyplot as plt
import numpy as np

import torchvision
import torchvision.transforms as transforms
import torchvision.models as models

import os
import util
import vggmodel
import argparse


def loadimgs(config, device):
    content_img = Image.open(config["content_img_dir"] + config["content"])
    style_img = Image.open(config["style_img_dir"] + config["style"])
    if config["shape"] == [-1, -1]:
        image_shape = (content_img.size[1] // 2, content_img.size[0] // 2)
    elif config["shape"][1] == -1:
        image_shape = (
            config["shape"][0],
            config["shape"][0] * content_img.size[0] // content_img.size[1],
        )
    else:
        image_shape = config["shape"]

    content_img = util.preprocess(content_img, image_shape, device)

    style_img = util.preprocess(style_img, image_shape, device)

    if config["init"] == "random":
        out_img = np.random.normal(loc=0, scale=255 / 2, size=content_img.shape).astype(
            np.float32
        )
        out_img = torch.from_numpy(out_img).to(device)
    elif config["init"] == "content":
        out_img = content_img.clone()
    elif config["init"] == "style":
        out_img = style_img.clone()
    out_img.requires_grad = True

    return content_img, style_img, out_img


def loadargs():
    data_dir = "./images"
    content_img_dir = f"{data_dir}/content/"
    style_img_dir = f"{data_dir}/style/"
    output_img_dir = f"{data_dir}/output/"
    img_format = ".jpg"

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--content", type=str, default="CBD.jpg", help="content image, default CBD"
    )
    parser.add_argument(
        "--style",
        type=str,
        default="StarryNight.jpg",
        help="style image, default StarryNight",
    )
    parser.add_argument(
        "--init",
        type=str,
        choices=["random", "content", "style"],
        default="content",
        help="init method of output image, default content",
    )
    parser.add_argument(
        "--content_weight",
        type=float,
        default=1e5,
        help="weight of content loss, default 1e5",
    )
    parser.add_argument(
        "--style_weight",
        type=float,
        default=5e4,
        help="weight of style loss, default 5e4",
    )
    parser.add_argument(
        "--tv_weight", type=float, default=1, help="weight of tv loss, default 1"
    )
    parser.add_argument(
        "--saving_freq",
        type=int,
        default=200,
        help="saving frequency of output images, default 200",
    )
    parser.add_argument(
        "--shape",
        type=int,
        nargs=2,
        default=[-1, -1],
        help='shape of output image, default "-1 -1" for shape of content image / 2, or "width -1" to set width and let height scale from content image, or "width height" for custom setting',
    )
    args = parser.parse_args()
    config = dict()
    for arg in vars(args):
        config[arg] = getattr(args, arg)
    config["content_img_dir"] = content_img_dir
    config["style_img_dir"] = style_img_dir
    config["output_img_dir"] = output_img_dir
    config["img_format"] = img_format
    return config


if __name__ == "__main__":
    print("Loading arguments...")
    config = loadargs()

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

    print("Preparing imagings and model...")
    print(f"content image: {config['content']}\nstyle image: {config['style']}")
    content_img, style_img, out_img = loadimgs(config, device)
    print("CNN model used: vgg19")
    model, content_index, style_indices = vggmodel.init_model(device)
    print("Extracting features from images...")
    content_feature = model(content_img)
    style_feature = model(style_img)
    target_content_representation = util.get_content_rep(content_feature, content_index)
    target_style_representation = util.get_style_rep(style_feature, style_indices)

    savedir = util.prepare_savedir(config)
    optimizer = optim.Adam((out_img,), lr=5)
    iterations = 3000

    content_weight, style_weight, tv_weight = (
        config["content_weight"],
        config["style_weight"],
        config["tv_weight"],
    )

    print("Iteration starts")
    for it in range(iterations):
        total_loss, content_loss, style_loss, tv_loss = util.get_gatys_loss(
            model,
            out_img,
            target_content_representation,
            content_index,
            target_style_representation,
            style_indices,
            content_weight,
            style_weight,
            tv_weight,
        )
        total_loss.backward()

        optimizer.step()
        optimizer.zero_grad()

        if it % 50 == 0 or it == iterations - 1:
            with torch.no_grad():
                print(
                    f"iteration: {it:04}, total loss={total_loss.item()}, content_loss={content_weight * content_loss.item()}, style loss={style_weight * style_loss.item()}, tv loss={tv_weight * tv_loss.item()}"
                )
                if it % 200 == 0 or it == iterations - 1:
                    torchvision.utils.save_image(
                        util.postprocess(out_img), f"{savedir}/iter{it:04}.jpg"
                    )