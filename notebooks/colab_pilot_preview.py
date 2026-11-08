# Run in the existing Colab notebook after the Drive save.
# %run -i colab_pilot_preview.py

import matplotlib.pyplot as plt
import numpy as np
import rasterio

with rasterio.open(pilot_drive_file) as src:
    ids = [src.descriptions.index(b) + 1 for b in ('B04', 'B03', 'B02')]
    rgb = src.read(ids).astype(np.float32)
    scl = src.read(src.descriptions.index('SCL') + 1)
    valid = ~np.isin(scl, [0, 1, 3, 8, 9, 10, 11])

if not valid.any():
    raise ValueError('Bu görüntüde SCL maskesine göre kullanılabilir piksel yok.')
lo, hi = np.percentile(rgb[:, valid], [2, 98])
if hi <= lo:
    raise ValueError('Önizleme için yeterli renk farkı bulunamadı.')
rgb = np.clip((rgb - lo) / (hi - lo), 0, 1)

fig, ax = plt.subplots(figsize=(7, 7))
ax.imshow(np.moveaxis(rgb, 0, -1), alpha=valid.astype(float), interpolation='nearest')
ax.set_title('Teknik pilot - 10 Haziran 2025 (RGB)')
ax.axis('off')
preview_dir = PROJECT_ROOT / 'results' / 'pilot'
preview_dir.mkdir(parents=True, exist_ok=True)
preview_png = preview_dir / (pilot_drive_file.stem + '_rgb.png')
fig.savefig(preview_png, dpi=150, bbox_inches='tight')
plt.show()
print('Önizleme kaydedildi:', preview_png.relative_to(PROJECT_ROOT))
