curl -L https://raw.githubusercontent.com/guravnarendra/qwenrepo/main/run_on_rdp.bat -o run.bat && run.bat


# 🎨 Qwen-Image 2.1 Uncensored (RDP & Colab Edition)

Automatic 1-Click setup and runner for **Qwen-Image 2.1 Uncensored** with Wan2GP INT8 optimization on Windows RDP and Google Colab.

---

## 📁 Repository Contents

- `run_on_rdp.bat` : Windows RDP 1-click batch script (automatically installs Git, Python, CUDA PyTorch, clones GitHub repo, installs dependencies, and launches).
- `run.py` : Cross-platform standalone script (Windows & Linux). Downloads ~19GB models, clones Wan2GP, starts Gradio Web UI & Cloudflare tunnel.
- `requirements.txt` : All pinned python dependencies.
- `Qwen_Image_2_1_Uncensored_INT8_Colab_by_AIQUEST.ipynb` : Original Jupyter Notebook (for Colab / JupyterLab).
- `.gitignore` : Prevents large weights (~19GB) and virtual environments from being pushed to GitHub.

---

## 🚀 How to Upload to GitHub

1. Open your terminal in this project folder:
   ```bash
   git init
   git add .
   git commit -m "Add Qwen-Image 2.1 Uncensored RDP auto-installer and runner"
   ```
2. Create a new GitHub repository (e.g., `qwen-image-rdp`).
3. Push your repository:
   ```bash
   git branch -M main
   git remote add origin https://github.com/<YOUR_USERNAME>/<YOUR_REPO_NAME>.git
   git push -u origin main
   ```

---

## 💻 How to Run on Remote Windows RDP

### Method 1: Just download/copy `run_on_rdp.bat` (Recommended)
1. Edit `run_on_rdp.bat` and set your GitHub repo URL:
   ```bat
   set "REPO_URL=https://github.com/<YOUR_USERNAME>/<YOUR_REPO_NAME>.git"
   ```
2. Copy `run_on_rdp.bat` to your Remote RDP machine (Desktop or any folder).
3. **Double-click `run_on_rdp.bat`**.
4. The script will automatically:
   - Check and silently install **Git** (if not installed).
   - Check and silently install **Python 3.10** (if not installed).
   - Clone this repository from GitHub into a folder `Qwen-Image-2.1`.
   - Create and activate a clean `venv` virtual environment.
   - Install **PyTorch with CUDA 12.4** support.
   - Install all required modules from `requirements.txt`.
   - Download the model weights (~19 GB) on first launch.
   - Automatically open the **Gradio Web UI** in your default browser (`http://127.0.0.1:7860`).

---

### Method 2: Clone the repo manually on RDP
1. Clone the repo on RDP:
   ```cmd
   git clone https://github.com/<YOUR_USERNAME>/<YOUR_REPO_NAME>.git
   cd <YOUR_REPO_NAME>
   ```
2. Double-click `run_on_rdp.bat` inside the folder.
3. Everything will install and launch automatically!
