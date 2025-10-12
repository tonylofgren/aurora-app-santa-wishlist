# Aurora Plugin – Santa's Wishlist

A standalone plugin for the [Aurora LLM Assistant](https://github.com/tony-aurora/aurora-llm-assistant) that keeps track of Christmas wishes. Families can register wishes, review what has already been sent to Santa and explore seasonal trends.

## Features

- Register wishes with optional age metadata.
- Retrieve all wishes stored for a specific child.
- Trending analytics summarising the most popular requests.
- Uses Aurora's isolated database manager for per-instance storage.
- Ships with English, Swedish, German and French translations.

## Installation

1. Clone this repository into Aurora's external plugin directory (normally `config/.storage/aurora_plugins/`):
   ```bash
   git clone https://github.com/tonylofgren/aurora-plugin-santa-wishlist.git \
     ~/.homeassistant/.storage/aurora_plugins/santa_wishlist
   ```
2. Restart Home Assistant or reload the Aurora integration so the plugin is detected.
3. Open the Aurora control panel and enable **Santa's Wishlist** under *Plugins*.

## Usage

The plugin exposes three LLM actions:

| Action      | Purpose                                                | Required fields          |
|-------------|--------------------------------------------------------|--------------------------|
| `register`  | Store a new wish                                       | `name`, `wish` (optional `age`)
| `list`      | Show every wish recorded for a specific child          | `name`, `age`
| `trending`  | Display trending wishes from the last 30 days          | *(none)*

Example prompts:
```text
- "Använd santa_wishlist med action='register', name='Lisa', age=7, wish='En röd sparkcykel'"
- "Ask santa_wishlist to list wishes for name='Alex' age=9"
- "Run santa_wishlist action='trending'"
```

## Development

The plugin follows the new centralized schema system (`BaseSchema`/`FieldSpec`) introduced in Aurora 2.4:

- Schema definitions live beside the tool class.
- Database operations flow through `DatabaseManager` to ensure per-instance isolation and rate limiting.
- Events are emitted via `event_manager.wish_registered` so automations can react instantly.

## License

Released under the MIT license. See [LICENSE](LICENSE) for details.
