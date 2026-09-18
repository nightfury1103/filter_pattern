"""Link/embed an already built compass without changing scanner decisions."""
from html import escape
import json
from os.path import relpath
from pathlib import Path


def compass_panel(output_file: Path, embed: bool = False) -> str:
    # Covers public/index.html and public/{d1,h4}/index.html; do not search
    # unrelated ancestors or add dead links to standalone scanner exports.
    folder = next((root/'compass' for root in (output_file.parent,output_file.parent.parent)
                   if (root/'compass/index.html').is_file() and (root/'compass/manifest.json').is_file()),None)
    if folder is None:
        return ''
    manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    href = escape(relpath(folder/'index.html',output_file.parent).replace('\\','/'),quote=True)
    stamp = escape(str(manifest.get('last_date') or 'chưa có dữ liệu'))
    available = int(manifest.get('available',0))
    note = f'D1 · {available}/7 mã · nến mới nhất {stamp} · XAUUSD dùng GC=F · thử nghiệm, chưa xác nhận 70%.'
    if manifest.get('provisional'):
        note += ' Có nến đang hình thành: '+escape(', '.join(manifest['provisional']))+'.'
    content = f'<section class="compass-published" style="margin:20px 0;padding:16px;border:1px solid #536174;border-radius:10px"><h2>Market Compass — thử nghiệm</h2><p>{note}</p><p><a href="{href}">Mở la bàn, hiệu suất và biểu đồ cả 7 mã</a></p>'
    if embed:
        content += f'<details><summary>Xem Market Compass tại đây</summary><iframe src="{href}" title="Market Compass D1 — thử nghiệm" loading="lazy" style="width:100%;height:1050px;border:0;margin-top:12px"></iframe></details>'
    return content+'</section>'
