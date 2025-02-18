Set shell = CreateObject("WScript.Shell")

' Check if virtual environment exists
If Not CreateObject("Scripting.FileSystemObject").FolderExists("venv") Then
    MsgBox "Virtual environment not found! Please run setup.bat first.", vbCritical, "Error"
    WScript.Quit
End If

' Activate the virtual environment and run the script silently
scriptPath = "venv\Scripts\pythonw.exe src\dh_hypso_gui.pyw"
shell.Run scriptPath, 0, False  ' 0 = No console, False = Don't wait for script to finish
