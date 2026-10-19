fn main() {
    let config = slint_build::CompilerConfiguration::new().with_style("fluent".into());
    if let Err(error) = slint_build::compile_with_config("ui/main.slint", config) {
        eprintln!("slint compile error: {error}");
        std::process::exit(1);
    }
}
