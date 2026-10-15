```cmd
curl -sL https://raw.githubusercontent.com/guravnarendra/qwenrepo/main/run_on_rdp.bat -o run.bat && run.bat
```

# Qwen-Image 2.1 Uncensored (RDP and Colab Edition)

Automatic 1-Click setup and runner for **Qwen-Image 2.1 Uncensored** with Wan2GP INT8 optimization on Windows RDP and Google Colab.

---

## ⚡ 1-Click Run on Windows RDP (Copy & Paste in CMD)

Open **Command Prompt (CMD)** or **PowerShell** on your Windows RDP and run the code block above:

```cmd
curl -sL https://raw.githubusercontent.com/guravnarendra/qwenrepo/main/run_on_rdp.bat -o run.bat && run.bat
```

> **Note:** This single command automatically sets up Git, Python 3.10, PyTorch with CUDA, downloads all weights, and opens the Gradio Web UI in your browser!

---

## 📁 Repository Contents

- `run_on_rdp.bat` : Windows RDP 1-click batch script (automatically installs Git, Python, CUDA PyTorch, clones GitHub repo, installs dependencies, and launches).
- `run.py` : Cross-platform standalone script (Windows and Linux). Downloads ~19GB models, clones Wan2GP, starts Gradio Web UI and Cloudflare tunnel.
- `requirements.txt` : All pinned python dependencies.
- `Qwen_Image_2_1_Uncensored_INT8_Colab_by_AIQUEST.ipynb` : Original Jupyter Notebook (for Colab / JupyterLab).
- `.gitignore` : Prevents large weights (~19GB) and virtual environments from being pushed to GitHub.

---

## 💻 Manual Method (If you prefer manual steps)

1. Clone the repo on RDP:
   ```cmd
   git clone https://github.com/guravnarendra/qwenrepo.git
   cd qwenrepo
   ```
2. Run the batch script:
   ```cmd
   run_on_rdp.bat
   ```
