# ==== GRADIO UI (simple) ======================================================
import gradio as gr
from PIL import Image
import numpy as np
import subprocess

# --- shared constants
GR_FPS = int(FPS)

def _sync_image_to_video(
    prompt: str,
    negative_prompt: str,
    duration_ui: float,
    seed_ui: int,
    randomize_seed: bool,
    ui_guidance_scale: float,
    improve_texture_flag: bool,
    height_ui: int,
    width_ui: int,
    image: Image.Image,
):
    """
    Synchronous wrapper: chạy pipeline và trả lại đường dẫn video mp4.
    """
    # guard
    if image is None:
        raise gr.Error("Vui lòng chọn ảnh đầu vào.")

    # lưu ảnh tạm
    tmp_img = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    image.save(tmp_img.name)
    input_image_path = tmp_img.name

    # seed
    s = random.randint(0, 2**32 - 1) if randomize_seed else int(seed_ui)
    seed_everething(s)

    # frames calc (giống code API)
    target_frames_ideal = duration_ui * FPS
    target_frames_rounded = max(1, round(target_frames_ideal))
    n_val = round((float(target_frames_rounded) - 1.0) / 8.0)
    actual_num_frames = int(n_val * 8 + 1)
    actual_num_frames = max(9, min(MAX_NUM_FRAMES, actual_num_frames))

    actual_height, actual_width = int(height_ui), int(width_ui)
    height_padded = ((actual_height - 1) // 32 + 1) * 32
    width_padded = ((actual_width - 1) // 32 + 1) * 32
    num_frames_padded = ((actual_num_frames - 2) // 8 + 1) * 8 + 1
    padding_values = calculate_padding(actual_height, actual_width, height_padded, width_padded)

    call_kwargs = {
        "prompt": prompt or "",
        "negative_prompt": negative_prompt or "",
        "height": height_padded,
        "width": width_padded,
        "num_frames": num_frames_padded,
        "frame_rate": GR_FPS,
        "generator": torch.Generator(device=target_inference_device).manual_seed(int(s)),
        "output_type": "pt",
        "conditioning_items": None,
        "media_items": None,
        "decode_timestep": PIPELINE_CONFIG_YAML["decode_timestep"],
        "decode_noise_scale": PIPELINE_CONFIG_YAML["decode_noise_scale"],
        "stochastic_sampling": PIPELINE_CONFIG_YAML["stochastic_sampling"],
        "image_cond_noise_scale": 0.15,
        "is_video": True,
        "vae_per_channel_normalize": True,
        "mixed_precision": (PIPELINE_CONFIG_YAML["precision"] == "mixed_precision"),
        "offload_to_cpu": False,
        "enhance_prompt": False,
    }

    # image conditioning
    media_tensor = load_image_to_tensor_with_resize_and_crop(
        input_image_path, actual_height, actual_width
    )
    media_tensor = torch.nn.functional.pad(media_tensor, padding_values)
    call_kwargs["conditioning_items"] = [
        ConditioningItem(media_tensor.to(target_inference_device), 0, 1.0)
    ]

    # run pipeline
    if improve_texture_flag and latent_upsampler_instance:
        multi_scale_pipeline_obj = LTXMultiScalePipeline(pipeline_instance, latent_upsampler_instance)
        first_pass_args = PIPELINE_CONFIG_YAML.get("first_pass", {}).copy()
        first_pass_args["guidance_scale"] = float(ui_guidance_scale)
        second_pass_args = PIPELINE_CONFIG_YAML.get("second_pass", {}).copy()
        second_pass_args["guidance_scale"] = float(ui_guidance_scale)

        multi_scale_call_kwargs = call_kwargs.copy()
        multi_scale_call_kwargs.update({
            "downscale_factor": PIPELINE_CONFIG_YAML["downscale_factor"],
            "first_pass": first_pass_args,
            "second_pass": second_pass_args,
        })

        result_images_tensor = multi_scale_pipeline_obj(**multi_scale_call_kwargs).images
    else:
        # single pass
        call_kwargs["guidance_scale"] = float(ui_guidance_scale)
        result_images_tensor = pipeline_instance(**call_kwargs).images

    # convert to video (mp4)
    video_np = result_images_tensor[0].permute(1, 2, 3, 0).cpu().float().numpy()
    video_np = np.clip(video_np, 0, 1)
    video_np = (video_np * 255).astype(np.uint8)

    temp_dir = tempfile.mkdtemp()
    output_video_path = os.path.join(temp_dir, f"ltx_out_{random.randint(10000,99999)}.mp4")

    with imageio.get_writer(output_video_path, fps=GR_FPS, macro_block_size=1) as writer:
        for f in video_np:
            writer.append_data(f)

    return output_video_path

def ui_generate(
    prompt, negative_prompt, duration_ui, seed_ui, randomize_seed,
    ui_guidance_scale, improve_texture_flag, height_ui, width_ui, image
):
    try:
        path = _sync_image_to_video(
            prompt, negative_prompt, duration_ui, seed_ui, randomize_seed,
            ui_guidance_scale, improve_texture_flag, height_ui, width_ui, image
        )
        return path
    except Exception as e:
        raise gr.Error(str(e))

def ui_last_frame(video_file):
    if video_file is None:
        raise gr.Error("Vui lòng chọn video.")
    try:
        reader = imageio.get_reader(video_file)
        last_frame = None
        for frame in reader:
            last_frame = frame
        reader.close()
        if last_frame is None:
            raise gr.Error("Không đọc được frame cuối.")
        out_img = os.path.join(tempfile.mkdtemp(), f"last_{random.randint(10000,99999)}.png")
        imageio.imwrite(out_img, last_frame)
        return out_img
    except Exception as e:
        raise gr.Error(str(e))

def ui_merge(videos):
    """
    videos: list các file video người dùng chọn ở UI.
    Dùng ffmpeg concat + re-encode (ổn định khi khác codec/fps).
    """
    if not videos:
        raise gr.Error("Chọn ít nhất 1 video.")
    tmp_dir = tempfile.mkdtemp()
    input_list_file = os.path.join(tmp_dir, "inputs.txt")
    out_mp4 = os.path.join(tmp_dir, f"merged_{uuid.uuid4().hex}.mp4")

    try:
        with open(input_list_file, "w", encoding="utf-8") as f:
            for v in videos:
                # gradio truyền path string
                f.write(f"file '{v}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", input_list_file,
            "-c:v", "libx264",
            "-c:a", "aac",
            out_mp4
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return out_mp4
    except subprocess.CalledProcessError as e:
        raise gr.Error(e.stderr.decode("utf-8", errors="ignore"))
    except Exception as e:
        raise gr.Error(str(e))

with gr.Blocks(title="LTX Image→Video", theme=gr.themes.Soft()) as demo:
    gr.Markdown("## 🎬 LTX Image → Video — Simple Gradio UI")

    with gr.Tab("Generate"):
        with gr.Row():
            with gr.Column(scale=3):
                prompt = gr.Textbox(label="Prompt", lines=4, placeholder="Describe motion/story…")
                negative = gr.Textbox(label="Negative Prompt", lines=3, placeholder="blurry, low quality…")
                image = gr.Image(label="Input Image", type="pil")
                gen_btn = gr.Button("Generate", variant="primary")
            with gr.Column(scale=2):
                duration = gr.Slider(0.5, 12.0, value=2.0, step=0.1, label="Duration (sec)")
                seed = gr.Number(value=42, precision=0, label="Seed")
                randomize = gr.Checkbox(value=True, label="Randomize seed")
                guidance = gr.Slider(1.0, 12.0, value=3.0, step=0.1, label="Guidance scale")
                improve = gr.Checkbox(value=True, label="Improve texture (multi-scale)")
                height = gr.Number(value=512, precision=0, label="Height")
                width = gr.Number(value=704, precision=0, label="Width")
                out_vid = gr.Video(label="Output Video")

        gen_btn.click(
            fn=ui_generate,
            inputs=[prompt, negative, duration, seed, randomize, guidance, improve, height, width, image],
            outputs=[out_vid]
        )

    with gr.Tab("Last Frame"):
        in_video = gr.Video(label="Pick a video")
        last_btn = gr.Button("Extract last frame")
        last_img = gr.Image(label="Last frame (PNG)")
        last_btn.click(ui_last_frame, inputs=[in_video], outputs=[last_img])

    with gr.Tab("Merge"):
        merge_files = gr.File(label="Pick multiple videos (ordered selection)", file_count="multiple", file_types=["video"])
        merge_btn = gr.Button("Merge")
        merged = gr.Video(label="Merged Output")
        merge_btn.click(ui_merge, inputs=[merge_files], outputs=[merged])

# Mount Gradio vào FastAPI tại /gradio
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
)
from fastapi.responses import RedirectResponse
try:
    from gradio.routes import mount_gradio_app
    app = mount_gradio_app(app, demo.queue(max_size=8, concurrency_count=1), path="/gradio")
except Exception:
    # fallback API nếu gradio API đổi
    from gradio import mount_gradio_app as _mount
    app = _mount(app, demo.queue(max_size=8, concurrency_count=1), path="/gradio")

# (tùy chọn) redirect root sang /gradio
@app.get("/")
def _root():
    return RedirectResponse(url="/gradio")
# ==============================================================================
