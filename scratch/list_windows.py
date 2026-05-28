import ctypes

def list_windows():
    EnumWindows = ctypes.windll.user32.EnumWindows
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    GetWindowText = ctypes.windll.user32.GetWindowTextW
    GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW
    IsWindowVisible = ctypes.windll.user32.IsWindowVisible
    GetClassName = ctypes.windll.user32.GetClassNameW

    windows = []

    def foreach_window(hwnd, lParam):
        if IsWindowVisible(hwnd):
            length = GetWindowTextLength(hwnd)
            buff = ctypes.create_unicode_buffer(length + 1)
            GetWindowText(hwnd, buff, length + 1)
            title = buff.value
            
            class_buff = ctypes.create_unicode_buffer(256)
            GetClassName(hwnd, class_buff, 256)
            class_name = class_buff.value
            
            if title or class_name:
                windows.append((hwnd, title, class_name))
        return True

    EnumWindows(EnumWindowsProc(foreach_window), 0)
    for hwnd, title, class_name in windows:
        print(f"HWND: {hwnd} | Class: {class_name} | Title: '{title}'")

if __name__ == "__main__":
    list_windows()
