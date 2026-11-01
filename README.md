# Ingredient Extractor for Home Assistant

Snap or pick a photo of a recipe and the ingredients — with amounts — land on your Home Assistant shopping list, one item each:

```
500g plain flour
2 tbsp olive oil
1 tsp baking powder
2 onions
salt and pepper
```

It is a custom integration plus a dashboard card in one HACS package. The card is loaded automatically, so there is no Lovelace resource to add.

- Reads printed, handwritten or on-screen recipes with a cloud vision model (Anthropic Claude Haiku by default).
- Uses structured JSON output from the model, not free-text parsing.
- Images are resized in the browser and processed in memory only — never saved to disk or logged.
- Adds to any `todo` entity; defaults to the built-in Shopping List (`todo.shopping_list`).

## Requirements

- Home Assistant 2026.3 or newer
- [HACS](https://hacs.xyz)
- An [Anthropic API key](https://console.anthropic.com/settings/keys)

## Install

1. **HACS → ⋮ → Custom repositories.** Add `https://github.com/esamwis3/ha-ingredient-extractor` with type **Integration**, then find **Ingredient Extractor** in HACS and select **Download**. Restart Home Assistant.
2. **Settings → Devices & services → Add integration → Ingredient Extractor.**
3. Choose the provider, paste your API key, pick a model (default `claude-haiku-5-5`) and select **Submit**. The key is checked before it is saved.
4. Edit a dashboard → **Add card** → search for **Ingredient Extractor**, or add it in YAML:

   ```yaml
   type: custom:ingredient-extractor-card
   title: Recipe to shopping list   # optional
   ```

Tap the card, choose a photo, and the added items appear on the card.

> If the card isn't found right after installing, hard-refresh the browser (or clear the Companion app's frontend cache) so the newly registered card script loads.

## Options

**Settings → Devices & services → Ingredient Extractor → Configure**

| Option | Default | |
|---|---|---|
| Model | `claude-haiku-5-5` | Any model your key can use; you can type a custom model ID. |
| Shopping list | `todo.shopping_list` | Any `todo` entity that supports adding items. |

Use **Reconfigure** on the integration to change the API key.

## How it works

1. The card shrinks the photo to at most 1568 px on the long edge and converts it to JPEG in the browser (iPhone HEIC photos included).
2. It posts the image to an authenticated Home Assistant endpoint, `/api/ingredient_extractor/extract`.
3. The integration checks the image type and size, sends it to the AI provider with a JSON schema, and validates the answer.
4. Each ingredient is formatted (`500g plain flour`, `2 tbsp olive oil`, `2 onions`) and added with `todo.add_item`.
5. The image bytes are dropped as soon as the request finishes.

Units are kept as written in the recipe, in short form. Items already on your list are not merged.

## Cost

With Claude Haiku 5.5 one photo is roughly 2,800 input and 500 output tokens — about **$0.0005 per recipe**, or under 2 cents a month at 30 recipes (Anthropic pricing, November 2026).

## Troubleshooting

| Card message | Meaning |
|---|---|
| That doesn't look like a recipe | The model found no recipe in the photo. Try a clearer shot of the ingredients list. |
| The AI provider rejected the API key | Use **Reconfigure** to enter a valid key. |
| That image format isn't supported | The browser couldn't convert the photo. Export it as JPEG or PNG. |
| The AI took too long to respond | The provider timed out (45 s). Try again. |

Debug logging:

```yaml
logger:
  logs:
    custom_components.ingredient_extractor: debug
```

## Privacy

Photos are sent to the AI provider you configure and are subject to its data policy. Nothing is stored by this integration. Your API key is kept in Home Assistant's config entry storage and never logged.

## Roadmap

- Take a photo with the camera
- Paste a recipe web link
- Add or sort ingredients manually
- More AI providers

## License

MIT
