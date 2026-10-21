fn main() {
    let config = slint_build::CompilerConfiguration::new().with_style("fluent".into());
    if let Err(error) = slint_build::compile_with_config("ui/main.slint", config) {
        eprintln!("slint compile error: {error}");
        std::process::exit(1);
    }
    // Windows: embed the application icon and version information in the .exe.
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("windows") {
        let mut resource = winresource::WindowsResource::new();
        resource
            .set_icon("assets/monooled.ico")
            .set("ProductName", "MonoOLED Studio")
            .set("FileDescription", "MonoOLED Studio")
            .set("LegalCopyright", "MIT License");
        if let Err(error) = resource.compile() {
            eprintln!("windows resource error: {error}");
            std::process::exit(1);
        }
    }
}
