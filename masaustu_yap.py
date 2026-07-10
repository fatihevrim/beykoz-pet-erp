import os
import subprocess
import sys

def create_desktop_shortcut():
    working_dir = os.path.dirname(os.path.abspath(__file__))
    target_path = os.path.join(working_dir, "BeykozPet_Baslat.bat")
    
    # Path to Desktop
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    shortcut_path = os.path.join(desktop, "Beykoz Pet ERP & POS.lnk")
    
    # Create temporary VBScript to write the Windows shortcut (.lnk file)
    vbs_script = f"""Set oWS = WScript.CreateObject("WScript.Shell")
sLinkFile = "{shortcut_path}"
Set oLink = oWS.CreateShortcut(sLinkFile)
oLink.TargetPath = "{target_path}"
oLink.WorkingDirectory = "{working_dir}"
oLink.Description = "Beykoz Pet AI ERP & POS Baslatici"
oLink.IconLocation = "%SystemRoot%\\System32\\shell32.dll,139"
oLink.Save()
"""
    
    vbs_path = os.path.join(working_dir, "create_lnk.vbs")
    
    try:
        # Write VBS script
        with open(vbs_path, "w", encoding="cp1254") as f:
            f.write(vbs_script)
            
        # Execute WScript
        subprocess.call(["wscript.exe", vbs_path], shell=True)
        
        # Clean up VBS script
        if os.path.exists(vbs_path):
            os.remove(vbs_path)
            
        print("==========================================================")
        print("BASARILI: Masaustune 'Beykoz Pet ERP & POS' kisayolu eklendi!")
        print("==========================================================")
        print(f"Kisayol Yolu: {shortcut_path}")
        print("Masaustundeki kisayola cift tiklayarak baslatabilirsiniz.")
        print("==========================================================")
        
    except Exception as e:
        print(f"Kisayol olusturulurken hata olustu: {e}")
        # Clean up just in case
        if os.path.exists(vbs_path):
            os.remove(vbs_path)

if __name__ == "__main__":
    create_desktop_shortcut()
