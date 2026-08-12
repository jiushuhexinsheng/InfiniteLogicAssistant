#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::menu::{Menu, MenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::{AppHandle, Manager};

#[tauri::command]
fn open_console(app: AppHandle) {
    if let Some(win) = app.get_webview_window("console") {
        let _ = win.show();
        let _ = win.unminimize();
        let _ = win.set_focus();
    } else {
        // 兜底：浏览器打开
        let _ = std::process::Command::new("cmd")
            .args(["/c", "start", "http://127.0.0.1:8520/console"])
            .spawn();
    }
}

#[tauri::command]
fn toggle_ball(app: AppHandle) {
    if let Some(win) = app.get_webview_window("ball") {
        let visible = win.is_visible().unwrap_or(false);
        if visible {
            let _ = win.hide();
        } else {
            let _ = win.show();
        }
    }
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![open_console, toggle_ball])
        .setup(|app| {
            let show = MenuItem::with_id(app, "show", "显示/隐藏悬浮球", true, None::<&str>)?;
            let open = MenuItem::with_id(app, "open", "打开控制台", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show, &open, &quit])?;
            TrayIconBuilder::with_id("main")
                .icon(app.default_window_icon().unwrap().clone())
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "show" => toggle_ball(app.app_handle().clone()),
                    "open" => open_console(app.app_handle().clone()),
                    "quit" => app.exit(0),
                    _ => {}
                })
                .build(app)?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
