import gradio as gr
import requests
import base64
import io
import os
from PIL import Image
from dotenv import load_dotenv
import argparse
import signal
import sys

# Load environment variables from .env file
load_dotenv()

def update_models(api_endpoint):
    try:
        response = requests.get("https://ir-api.myqa.cc/v1/openai/images/models")
        response.raise_for_status()
        models = response.json()
        model_names = list(models.keys())
        if api_endpoint == "https://api.openai.com/v1/images/":
            # Only keep models that start with "openai/" when hitting the OpenAI endpoint
            filtered = [m.replace("openai/", "") for m in model_names if m.startswith("openai/")]  # list[str]
            return filtered
        else:
            # For ImageRouter or any other endpoint, expose *all* models as their raw names.
            # The UI can still allow the user to type custom values if needed.
            return model_names
    except Exception as e:
        print('error', e, flush=True)
        return []

def generate_image(prompt, api_key, model, quality, api_endpoint, custom_endpoint):    
    print('generate_image', prompt, api_key, model, quality, api_endpoint, custom_endpoint, flush=True)
    actual_endpoint = get_actual_endpoint(api_endpoint, custom_endpoint)
    print('actual_endpoint', actual_endpoint, flush=True)
    n = 1
    payload = {
        "prompt": prompt,
        "model": model,
        "quality": quality
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    try:
        response = requests.post(
            f"{actual_endpoint}/generations",
            headers=headers,
            json=payload
        )
        response.raise_for_status()
        
        result = response.json()

        print(result, flush=True)
        
        if "data" in result and len(result["data"]) > 0:
            if "url" in result["data"][0]:
                images = [result["data"][i]["url"] for i in range(len(result["data"]))]
                return images, gr.update(visible=False, value="")
            elif "b64_json" in result["data"][0]:
                images = []
                for i in range(len(result["data"])):
                    img_data = base64.b64decode(result["data"][i]["b64_json"])
                    img = Image.open(io.BytesIO(img_data))
                    images.append(img)
                return images, gr.update(visible=False, value="")
        
        return [], gr.update(visible=True, value="No output received")
    except Exception as e:
        print(e, flush=True)
        return [], gr.update(visible=True, value=str(e))

def edit_image(image, mask, prompt, api_key, model, quality, api_endpoint, custom_endpoint):
    actual_endpoint = get_actual_endpoint(api_endpoint, custom_endpoint)
    if image is None:
        return None, gr.update(visible=True, value="Please upload an image to edit")
    
    headers = {
        "Authorization": f"Bearer {api_key}"
    }
    
    # Convert image to bytes
    image_bytes = io.BytesIO()
    image.save(image_bytes, format="PNG")
    image_bytes.seek(0)
    
    # Prepare mask if provided
    mask_bytes = None
    if mask is not None:
        mask_bytes = io.BytesIO()
        mask.save(mask_bytes, format="PNG")
        mask_bytes.seek(0)
    
    files = {
        "image": ("image.png", image_bytes, "image/png"),
        "prompt": (None, prompt)
    }
    
    if mask_bytes:
        files["mask"] = ("mask.png", mask_bytes, "image/png")
    
    if model:
        files["model"] = (None, model)
    
    if quality:
        files["quality"] = (None, quality)
    
    try:
        response = requests.post(
            f"{actual_endpoint}/edits",
            headers=headers,
            files=files
        )
        response.raise_for_status()
        
        result = response.json()
        
        if "data" in result and len(result["data"]) > 0:
            if "url" in result["data"][0]:
                return result["data"][0]["url"], gr.update(visible=False, value="")
            elif "b64_json" in result["data"][0]:
                img_data = base64.b64decode(result["data"][0]["b64_json"])
                img = Image.open(io.BytesIO(img_data))
                return img, gr.update(visible=False, value="")
        
        return None, gr.update(visible=True, value="No output received")
    except Exception as e:
        return None, gr.update(visible=True, value=str(e))

def update_endpoint_visibility(choice):
    if choice == "Custom":
        return gr.update(visible=True)
    else:
        return gr.update(visible=False)

def get_actual_endpoint(choice, custom_endpoint):
    print('get_actual_endpoint', choice, custom_endpoint, flush=True)
    if choice == "OpenAI":
        return "https://api.openai.com/v1/images"
    elif choice == "ImageRouter":
        return "https://ir-api.myqa.cc/v1/openai/images"
    else:  # Custom
        return custom_endpoint

def update_dropdowns(choice, custom):
    models = update_models(get_actual_endpoint(choice, custom))
    return gr.update(choices=models, value=None), gr.update(choices=models, value=None)

with gr.Blocks(title="OpenAI Image Generator & Editor") as app:
    gr.Markdown("# OpenAI Image Generator & Editor")
    
    with gr.Tab("Settings"):
        gr.Markdown("Get OpenAI API key: https://platform.openai.com")
        gr.Markdown("Get ImageRouter API key: https://ir.myqa.cc/")
        
        with gr.Row():
            api_endpoint_choice = gr.Radio(
                choices=["OpenAI", "ImageRouter", "Custom"],
                label="API Endpoint",
                value="Custom" if os.environ.get("API_ENDPOINT", "") != "" else None
            )
        
        with gr.Row():
            custom_endpoint = gr.Textbox(
                label="Custom API Endpoint", 
                placeholder="Enter your custom API endpoint (e.g., https://your-api.com/v1/images/)",
                visible=os.environ.get("API_ENDPOINT", "") != "",
                value=os.environ.get("API_ENDPOINT", "")
            )
        
        api_key = gr.Textbox(
            label="API Key", 
            placeholder="Enter your API key", 
            type="password",
            value=os.environ.get("API_KEY", "")
        )
    
    with gr.Tab("Generate Images"):
        with gr.Row():
            with gr.Column():
                gen_prompt = gr.Textbox(label="Prompt", placeholder="Describe the image you want to generate", lines=5)
                gen_model = gr.Dropdown(choices=[], label="Model", allow_custom_value=True)
                
                with gr.Row():
                    gen_quality = gr.Dropdown(
                        choices=["auto", "low", "medium", "high"],
                        label="Quality",
                        value="auto"
                    )
                
                gen_button = gr.Button("Generate")
            
            with gr.Column():
                gen_output = gr.Gallery(label="Generated Images")
                gen_error = gr.Textbox(label="Error Message", visible=False)
    
    with gr.Tab("Edit Images"):
        with gr.Row():
            with gr.Column():
                edit_image_input = gr.Image(label="Upload Image to Edit", type="pil")
                edit_mask = gr.Image(label="Upload Mask (Optional)", type="pil")
                edit_prompt = gr.Textbox(label="Prompt", placeholder="Describe the edit you want to make", lines=5)
                edit_model = gr.Dropdown(choices=[], label="Model", allow_custom_value=True)
                
                edit_quality = gr.Dropdown(
                    choices=["auto", "low", "medium", "high"],
                    label="Quality",
                    value="auto"
                )
                
                edit_button = gr.Button("Edit Image")
            
            with gr.Column():
                edit_output = gr.Image(label="Edited Image")
                edit_error = gr.Textbox(label="Error Message", visible=False)
    
    # Handle visibility of custom endpoint textbox
    api_endpoint_choice.change(
        fn=update_endpoint_visibility, 
        inputs=[api_endpoint_choice], 
        outputs=[custom_endpoint]
    )
    
    # Update models when api endpoint or custom endpoint changes using the new helper
    api_endpoint_choice.change(
        fn=update_dropdowns,
        inputs=[api_endpoint_choice, custom_endpoint],
        outputs=[gen_model, edit_model]
    )
    
    custom_endpoint.change(
        fn=update_dropdowns,
        inputs=[api_endpoint_choice, custom_endpoint],
        outputs=[gen_model, edit_model]
    )
    
    gen_button.click(
        fn=generate_image,
        inputs=[gen_prompt, api_key, gen_model, gen_quality, api_endpoint_choice, custom_endpoint],
        outputs=[gen_output, gen_error]
    )
    
    edit_button.click(
        fn=edit_image,
        inputs=[edit_image_input, edit_mask, edit_prompt, api_key, edit_model, edit_quality, api_endpoint_choice, custom_endpoint],
        outputs=[edit_output, edit_error]
    )

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--server_name", type=str, default="127.0.0.1")
    parser.add_argument("--server_port", type=int, default=7860)
    args = parser.parse_args()

    def sigterm_handler(signum, frame):
        print("Received SIGTERM, shutting down gracefully...")
        app.close()
        sys.exit(0)

    signal.signal(signal.SIGTERM, sigterm_handler)
    
    app.launch(server_name=args.server_name, server_port=args.server_port) 