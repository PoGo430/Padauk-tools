import os
import platform
import subprocess

def build_executable():
    # Install requirements if not already installed
    subprocess.run(['pip', 'install', '-r', 'requirements.txt'])
    
    # Base PyInstaller command
    base_cmd = [
        'pyinstaller',
        '--onefile',
        '--windowed',  # This prevents the terminal window from appearing
        '--name', 'Padauk Tools',
        'Padauk Tools.py'
    ]
    
    # Add icon if available (you can add an .ico file later)
    # if os.path.exists('icon.ico'):
    #     base_cmd.extend(['--icon', 'icon.ico'])
    
    # Build the executable
    subprocess.run(base_cmd)
    
    print("\nBuild completed!")
    print(f"Executable can be found in the 'dist' directory")

if __name__ == "__main__":
    build_executable() 
