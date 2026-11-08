# Run in the existing Colab notebook after the small download:
# %run -i colab_pilot_save.py

import hashlib
import json
import shutil
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4

import numpy as np
import rasterio
from shapely.geometry import mapping
from sentinel_crop_pipeline.discovery.providers.cdse import CdseProvider


def save_pilot_to_drive(source, project_root, scene, aoi, bands):
    source, project_root = Path(source), Path(project_root)
    if not source.is_file():
        raise FileNotFoundError('Colab geçici dosyası bulunamadı. Drive kaydı tamamlanmadan çalışma zamanı kapanmış olabilir.')
    if not project_root.is_dir():
        raise FileNotFoundError('Drive proje klasörü bulunamadı. Önce Drive bağlantısını kontrol edin.')

    epsg, bounds, width, height = CdseProvider()._utm_bbox(aoi, 10)
    expected_bands = tuple(bands) + ('SCL',)

    def sha256(path):
        digest = hashlib.sha256()
        with Path(path).open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        return digest.hexdigest()

    def inspect(path):
        with rasterio.open(path) as src:
            if src.descriptions != expected_bands or src.dtypes != ('uint16',) * len(expected_bands):
                raise ValueError('Raster bantları veya veri türü beklenenden farklı.')
            if not src.crs or src.crs.to_epsg() != epsg or (src.width, src.height) != (width, height):
                raise ValueError('Raster koordinat sistemi veya boyutları beklenenden farklı.')
            if not np.allclose(src.bounds, bounds, rtol=0, atol=1e-6) or not np.allclose(src.res, (10, 10), rtol=0, atol=1e-9):
                raise ValueError('Raster gridi beklenenden farklı.')
            if not np.any(src.read(list(range(1, len(bands) + 1))) > 0):
                raise ValueError('Optik bantlarda veri bulunamadı.')
            scl = src.read(len(expected_bands))
            if not np.isin(scl, np.arange(12)).all() or not np.any(scl != 0):
                raise ValueError('SCL kalite katmanı geçersiz veya boş.')
            return {
                'crs': src.crs.to_string(),
                'width': src.width,
                'height': src.height,
                'bounds': list(src.bounds),
                'transform': list(src.transform)[:6],
                'resolution': list(src.res),
                'band_names': list(src.descriptions),
                'dtypes': list(src.dtypes),
                'scl_usable_pixel_pct': float(100 * np.mean(~np.isin(scl, [0, 1, 3, 8, 9, 10, 11]))),
            }

    raster_info = inspect(source)
    digest = sha256(source)
    day = scene.datetime[:10]
    request = {
        'collection': 'sentinel-2-l2a',
        'endpoint': 'https://sh.dataspace.copernicus.eu/api/v1/process',
        'time_range_utc': {'from': f'{day}T00:00:00Z', 'to': f'{day}T23:59:59Z'},
        'aoi_epsg4326': mapping(aoi),
        'output_resolution_m': 10,
        'bands': list(expected_bands),
        'units': 'DN',
        'sample_type': 'UINT16',
        'resampling': 'NEAREST',
        'harmonizeValues': {'sent_in_request': False, 'documented_api_default': True},
        'mosaickingOrder': {'sent_in_request': False, 'documented_api_default': 'mostRecent'},
    }
    request_id = hashlib.sha256(json.dumps(request, sort_keys=True).encode('utf-8')).hexdigest()[:16]
    output_dir = project_root / 'raw' / 'pilot'
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f'urla_pilot_{day.replace("-", "")}_{request_id}.tif'
    record = target.with_suffix('.json')

    if record.exists():
        try:
            existing = json.loads(record.read_text(encoding='utf-8'))
        except (ValueError, OSError):
            raise RuntimeError('Mevcut kontrol kaydı okunamadı; üzerine yazılmadı.') from None
        if not isinstance(existing, dict) or existing.get('sha256') != digest or existing.get('request_id') != request_id:
            raise RuntimeError('Mevcut kontrol kaydı farklı bir dosyaya ait; üzerine yazılmadı.')

    partial = target.with_name(target.name + f'.{uuid4().hex}.partial')
    partial_record = record.with_name(record.name + f'.{uuid4().hex}.partial')
    try:
        if not target.exists():
            shutil.copyfile(source, partial)
            inspect(partial)
            if sha256(partial) != digest:
                raise RuntimeError('Drive aktarımının SHA256 kontrolü başarısız.')
            if not target.exists():
                partial.rename(target)
        if sha256(target) != digest:
            raise RuntimeError('Drive hedefinde farklı veya eksik bir dosya var; üzerine yazılmadı.')
        drive_info = inspect(target)
        if drive_info != raster_info:
            raise RuntimeError('Drive kopyasının raster bilgileri kaynakla eşleşmiyor.')

        if not record.exists():
            metadata = {
                'schema_version': 1,
                'purpose': 'technical_pilot_not_a_final_training_dataset',
                'created_utc': datetime.now(timezone.utc).isoformat(),
                'package_version': version('sentinel-crop-pipeline'),
                'request_id': request_id,
                'request': request,
                'candidate_reference': {
                    'id': scene.id,
                    'datetime': scene.datetime,
                    'cloud_cover_pct': scene.cloud_cover,
                    'geometry': scene.geometry,
                },
                'exact_source_product_ids_verified': False,
                'source_selection_note': 'Process API filters the full UTC day; the candidate reference is not verified as the exclusive source.',
                'actual_source_processing_baselines': None,
                'processing_documentation': 'https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/S2L2A.html',
                'raster': drive_info,
                'sha256': digest,
                'size_bytes': target.stat().st_size,
                'project_relative_path': target.relative_to(project_root).as_posix(),
                'pixels_rewritten_or_normalized': False,
                'scientific_quality_accepted': False,
            }
            partial_record.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
            if not record.exists():
                partial_record.rename(record)
        persisted = json.loads(record.read_text(encoding='utf-8'))
        if persisted.get('sha256') != digest or persisted.get('request_id') != request_id:
            raise RuntimeError('Drive kontrol kaydının doğrulaması başarısız.')
    finally:
        for staging_file in (partial, partial_record):
            if staging_file.is_file():
                staging_file.unlink()

    print('Drive kopyası ve SHA256 kontrolü tamamlandı.')
    print('Görüntü:', target.relative_to(project_root).as_posix())
    print('Kontrol kaydı:', record.relative_to(project_root).as_posix())
    return target


if __name__ == '__main__':
    pilot_drive_file = save_pilot_to_drive(
        pilot_file, PROJECT_ROOT, pilot_scene, download_aoi, pilot_bands
    )
