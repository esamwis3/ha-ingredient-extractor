# Ingredient Extractor for Home Assistant

Snap a photo of a recipe, paste a recipe link, or share one from your phone's browser, and the ingredients — with amounts — land on your Home Assistant shopping list, one item each:

```
500g plain flour
2 tbsp olive oil
1 tsp baking powder
2 onions
salt and pepper
```

It is a custom integration plus a dashboard card in one HACS package. The card is loaded automatically, so there is no Lovelace resource to add.

- Reads printed, handwritten or on-screen recipes with a cloud vision model (Anthropic Claude Haiku by default).
- Also reads plain shopping lists (a whiteboard, fridge door or notepad), one item per line, with or without amounts.
- Combines duplicates: `500g plain flour` already on the list plus `200g plain flour` becomes `700g plain flour`.
- Sorts the list by shop section (vegetables, fruit, meat, dairy…), automatically after each recipe or on demand.
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
   camera: auto                     # optional: auto (default), true or false
   android_camera: viewfinder       # optional: viewfinder (default) or native
   layout: inline                   # optional: inline (default) or fab
   ```

On a phone or tablet the card shows **Take photo** and **Choose photo** (your photo library). On iPhone, Take photo opens the native camera; on Android, where the Companion app always opens the media picker, it opens a live viewfinder in the card instead (allow camera access when asked); on a desktop it shows a single box you can click or drop a photo onto. `camera: true` or `false` forces either layout. Once your Android Companion app opens the camera from web pages (support was merged in October 2026 and is not in release 2026.10.1), set `android_camera: native` to use the phone's own camera app instead of the viewfinder.

> If the card isn't found right after installing, hard-refresh the browser (or clear the Companion app's frontend cache) so the newly registered card script loads.

### Floating button layout

`layout: fab` keeps the dashboard free for the list itself: the card shows a floating **+ Recipe** button (bottom right, above a floating navbar) that opens a bottom sheet with Take photo, Choose photo and the link field. Success closes the sheet and shows a toast. Place the card **after** your list — in this layout it only adds a small spacer so the last item isn't hidden under the button. Options: `fab_label` (default `Recipe`), `fab_bottom` (default `108px`), `fab_right` (default `16px`). Both offsets are added to the safe-area inset Home Assistant reports (the same one navbar-card uses), so the button stays put relative to a floating navbar in the iPhone and Android apps.

### Recipe links

- **Paste a link:** paste a recipe URL into the link field — it's sent automatically (or tap **+**). On Android, Gboard shows your copied link above the keyboard: one tap pastes and sends it.
- **Share from Android:** in your phone's browser, tap Share → **Home Assistant**. The ingredients are added in the background and you get a notification on that phone ("Added 12 items from Chicken Curry"). Turn this off under the integration's **Configure** options.

Most recipe sites publish their ingredients as structured data (schema.org Recipe), which is used when present; otherwise the page text is read. Some sites block automated access — use a photo for those. Links to local network addresses are refused.

## Options

**Settings → Devices & services → Ingredient Extractor → Configure**

| Option | Default | |
|---|---|---|
| API key | (from setup) | Leave blank to keep the current key. A new key is checked with Anthropic before it is saved. |
| Model | `claude-haiku-5-5` | Any model your key can use; you can type a custom model ID. |
| Shopping list | `todo.shopping_list` | Any `todo` entity that supports adding items. |
| Add recipes shared to the Home Assistant app | on | Android only: links shared to the app are added in the background, with a notification. |
| Sort the list after adding | on | After a photo or link is added, order the open items by shop section. |

You can also change the API key and model with **Reconfigure**.

## How it works

1. The card shrinks the photo to at most 1568 px on the long edge and converts it to JPEG in the browser (iPhone HEIC photos included).
2. It posts the image to an authenticated Home Assistant endpoint, `/api/ingredient_extractor/extract`.
3. The integration checks the image type and size, sends it to the AI provider with a JSON schema, and validates the answer.
4. Each ingredient is formatted (`500g plain flour`, `2 tbsp olive oil`, `2 onions`) and added with `todo.add_item`.
5. The image bytes are dropped as soon as the request finishes.

Units are kept as written in the recipe, in short form. When a recipe prints a metric amount alongside an imperial one ("2 lbs (908 g)", "1 cup (240 ml)", "1 can (420 g)"), the metric amount is used; spoon measures and whole items ("2 tsp paprika", "1 red pepper") stay as written.

### Duplicates

Before adding an item, the integration looks for an open (unticked) entry with the same name, ignoring amounts, case and plurals:

- Amounts in the same unit, or in g/kg or ml/l, are added up: `1kg mince` + `500g mince` → `1.5kg mince`, `1 onion` + `2 onions` → `3 onions`.
- A bare name adds nothing to an entry with an amount, and the other way round the amount wins: `milk` + `500ml milk` → `500ml milk`; `milk` + `milk` stays one `milk`.
- Amounts that can't be added up (`2 tbsp olive oil` and `100ml olive oil`) stay as separate items. So do different names (`red onions` and `onions`).

Ticked items are never changed.

### Sorting

Each extracted item comes back with a shop section, in this order: Vegetables, Fruit, Meat, Dairy, Confectionery, Tins of food, Crisps, Alcohol, Medicine, Frozen food, Household, Baking, Bread, Cereal and breakfast, Tea, coffee and hot drinks, then Other.

The action `ingredient_extractor.sort_list` orders the open items by section, keeping the order within a section, with ticked items below. Items typed by hand or added by voice are classified in one small AI call the first time they're seen; every item's section is remembered (in `.storage/ingredient_extractor.categories`), so sorting again costs nothing. A Sort button on a dashboard:

```yaml
type: button
icon: mdi:sort-variant
tap_action:
  action: perform-action
  perform_action: ingredient_extractor.sort_list
```

## Cost

With Claude Haiku 5.5 one photo is roughly 2,800 input and 700 output tokens — about **$0.0006 per recipe**; a link with structured recipe data is about **$0.0002**. Under 2 cents a month at 30 recipes (Anthropic pricing, November 2026).

## Troubleshooting

| Card message | Meaning |
|---|---|
| That doesn't look like a recipe or shopping list | The model found no recipe or list in the photo. Try a clearer shot of the ingredients list. |
| The AI provider rejected the API key | Enter a valid key under **Configure** (or **Reconfigure**). |
| That image format isn't supported | The browser couldn't convert the photo. Export it as JPEG or PNG. |
| The AI took too long to respond | The provider timed out (45 s). Try again. |
| "Configuration error" right after Home Assistant restarts | The page loaded before the integration finished starting, so the card script wasn't included. Refresh the page (in the Companion app: Settings → Companion app → Debugging → Reset frontend cache). |
| Take photo opens the photo picker | On Android the card uses its own viewfinder; allow camera access for the Home Assistant app when asked. |

Debug logging:

```yaml
logger:
  logs:
    custom_components.ingredient_extractor: debug
```

## Privacy

Photos are sent to the AI provider you configure and are subject to its data policy. Nothing is stored by this integration. Your API key is kept in Home Assistant's config entry storage and never logged.

## Roadmap

- Add or sort ingredients manually
- More AI providers

## License

MIT
