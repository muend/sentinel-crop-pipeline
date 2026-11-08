# Run in the existing Colab notebook after the catalog search:
# %run -i colab_pilot_download.py

from tempfile import mkdtemp
from shapely.geometry import box, shape
import numpy as np
import rasterio

download_aoi = box(26.78, 38.25, 26.83, 38.29)
pilot_scene = next((s for s in pilot_scenes
    if s.datetime[:10] == '2025-06-10'
    and s.geometry and shape(s.geometry).covers(download_aoi)), None)
if pilot_scene is None:
    raise RuntimeError('10 Haziran için bu küçük alanı kapsayan aday bulunamadı.')

pilot_bands = ['B02', 'B03', 'B04', 'B08']
download_provider = CdseProvider({
    'preprocessing': {'resampling': 'nearest'},
    'download': {'max_auto_size_mb': 10},
})
pilot_workdir = Path(mkdtemp(prefix='sentinel_pilot_'))
pilot_file = download_provider.download(
    pilot_scene, download_aoi, pilot_bands, pilot_workdir, resolution_m=10
)
epsg, expected_bounds, width, height = download_provider._utm_bbox(download_aoi, 10)

with rasterio.open(pilot_file) as src:
    assert src.descriptions == tuple(pilot_bands + ['SCL']), 'Bant sırası beklenenden farklı.'
    assert src.dtypes == ('uint16',) * 5, 'Veri türü beklenenden farklı.'
    assert src.crs and src.crs.to_epsg() == epsg, 'Koordinat sistemi beklenenden farklı.'
    assert (src.width, src.height) == (width, height), 'Görüntü boyutu beklenenden farklı.'
    assert np.allclose(src.bounds, expected_bounds) and np.allclose(src.res, (10, 10)), 'Görüntü gridi beklenenden farklı.'
    assert np.any(src.read([1, 2, 3, 4]) > 0), 'Optik bantlarda veri bulunamadı.'
    scl = src.read(5)
    assert np.isin(scl, np.arange(12)).all() and np.any(scl != 0), 'SCL kalite katmanı geçersiz veya boş.'
    pilot_valid_pct = float(100 * np.mean(~np.isin(scl, [0, 1, 3, 8, 9, 10, 11])))

print('Deneme dosyası Colab içinde doğrulandı.')
print('Dosya boyutu (MB):', round(pilot_file.stat().st_size / 1e6, 2))
print('SCL maskesine göre kullanılabilir piksel (%):', round(pilot_valid_pct, 1))
