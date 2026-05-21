"""
Baixador de edições do DOE-PE — Poder Executivo.

URL de origem:
  https://cepebr-prod.s3.amazonaws.com/1/cadernos/{ano}/{AAAAMMDD}/
  1-PoderExecutivo/PoderExecutivo({AAAAMMDD}).pdf

Arquivo salvo como:
  executivo/PoderExecutivoAAAAMMDD.pdf  (sem parênteses)

Uso:
  python src/downloader.py                         # hoje (modo tarefa diária)
  python src/downloader.py --date 2024-12-27       # data específica
  python src/downloader.py --start 2024-01-01      # do início até hoje
  python src/downloader.py --start 2024-01-01 --end 2024-12-31
  python src/downloader.py --days 90               # últimos 90 dias
"""

import argparse
import logging
import sys
import time
import urllib.request
import urllib.error
from datetime import date, timedelta
from pathlib import Path

# ── Constantes ────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent
EXECUTIVO_DIR = PROJECT_ROOT / "executivo"
LOG_DIR = PROJECT_ROOT / "logs"

_BASE_URL = (
    "https://cepebr-prod.s3.amazonaws.com/1/cadernos"
    "/{year}/{ymd}/1-PoderExecutivo/PoderExecutivo({ymd}).pdf"
)

_HEADERS = {"User-Agent": "DOE-PE-Downloader/1.0 (+https://www.igpe.pe.gov.br)"}

# HTTP 403 e 404 indicam edição não publicada — não adianta tentar novamente
_NO_EDITION_CODES = {403, 404}

# Dias sem publicação habitual (0=seg … 6=dom)
_DIAS_SEM_PUBLICACAO = {6}  # domingo; sábado pode ter edição extra


# ── Helpers ───────────────────────────────────────────────────────────────────

def _url(d: date) -> str:
    ymd = d.strftime("%Y%m%d")
    return _BASE_URL.format(year=d.year, ymd=ymd)


def _dest(d: date, out_dir: Path) -> Path:
    return out_dir / f"PoderExecutivo{d.strftime('%Y%m%d')}.pdf"


def _setup_logging(log_file: Path | None = None) -> None:
    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout)
    ]
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(
            logging.FileHandler(log_file, encoding="utf-8", mode="a")
        )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)-8s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
        force=True,
    )


# ── Download de uma edição ────────────────────────────────────────────────────

def download_edition(d: date, out_dir: Path, retries: int = 3) -> str:
    """
    Tenta baixar a edição da data `d`.

    Retorna:
      'ok'         — baixado com sucesso
      'exists'     — arquivo já existia
      'no_edition' — não há edição nesta data (404/403)
      'error'      — falha de rede após retentativas
    """
    dest = _dest(d, out_dir)

    if dest.exists():
        logging.info("%s: já existe (%s), pulando.", d, dest.name)
        return "exists"

    url = _url(d)
    logging.info("%s: baixando %s", d, url)

    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()

            dest.write_bytes(data)
            logging.info(
                "%s: OK - %s (%s bytes)", d, dest.name, f"{len(data):,}"
            )
            return "ok"

        except urllib.error.HTTPError as e:
            if e.code in _NO_EDITION_CODES:
                logging.warning(
                    "%s: sem edição disponível (HTTP %s).", d, e.code
                )
                return "no_edition"
            logging.error(
                "%s: HTTP %s — tentativa %d/%d.", d, e.code, attempt, retries
            )

        except urllib.error.URLError as e:
            logging.error(
                "%s: erro de rede (%s) — tentativa %d/%d.", d, e.reason, attempt, retries
            )

        except OSError as e:
            logging.error("%s: erro ao salvar arquivo: %s", d, e)
            return "error"

        except Exception as e:  # noqa: BLE001
            logging.error("%s: erro inesperado: %s", d, e)
            return "error"

        if attempt < retries:
            wait = 5 * attempt
            logging.info("%s: aguardando %ds antes de tentar novamente…", d, wait)
            time.sleep(wait)

    logging.error("%s: todas as tentativas falharam.", d)
    return "error"


# ── Download de intervalo ─────────────────────────────────────────────────────

class Summary:
    def __init__(self):
        self.ok = self.exists = self.no_edition = self.error = 0

    def record(self, result: str) -> None:
        match result:
            case "ok":         self.ok += 1
            case "exists":     self.exists += 1
            case "no_edition": self.no_edition += 1
            case _:            self.error += 1

    def log(self) -> None:
        logging.info(
            "Concluido - baixados: %d | ja existiam: %d "
            "| sem edicao: %d | erros: %d",
            self.ok, self.exists, self.no_edition, self.error,
        )


def download_range(
    start: date,
    end: date,
    out_dir: Path,
    skip_sundays: bool = True,
) -> Summary:
    summary = Summary()
    total = (end - start).days + 1
    logging.info("Intervalo: %s -> %s (%d dias)", start, end, total)

    d = start
    while d <= end:
        if skip_sundays and d.weekday() in _DIAS_SEM_PUBLICACAO:
            logging.debug("%s: domingo, pulando.", d)
            d += timedelta(days=1)
            continue

        result = download_edition(d, out_dir)
        summary.record(result)

        # Pequena pausa entre downloads para não sobrecarregar o servidor
        if result == "ok":
            time.sleep(1)

        d += timedelta(days=1)

    return summary


# ── Modo diário (tarefa agendada) ─────────────────────────────────────────────

def run_daily(out_dir: Path) -> None:
    """
    Modo para tarefa agendada: baixa a edição de hoje.
    Se não houver edição hoje, avisa sem falhar (exit 0).
    """
    today = date.today()
    logging.info("=== Tarefa diária — %s ===", today)

    result = download_edition(today, out_dir)

    if result == "no_edition":
        logging.info(
            "Edição de %s não disponível. "
            "Pode ser feriado, fim de semana ou publicação atrasada.", today
        )
    elif result == "error":
        logging.error("Falha ao baixar edição de %s.", today)
        sys.exit(1)  # sinaliza erro para o Task Scheduler

    logging.info("=== Tarefa diária concluída ===")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Baixa edições do DOE-PE Poder Executivo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--date", metavar="YYYY-MM-DD",
        help="Baixa uma data específica",
    )
    mode.add_argument(
        "--start", metavar="YYYY-MM-DD",
        help="Início do intervalo (vai até --end ou hoje)",
    )
    mode.add_argument(
        "--days", type=int, metavar="N",
        help="Baixa os últimos N dias (padrão: modo diário = só hoje)",
    )

    parser.add_argument(
        "--end", metavar="YYYY-MM-DD",
        help="Fim do intervalo (usado com --start)",
    )
    parser.add_argument(
        "--out", metavar="DIR",
        help=f"Pasta de destino (padrão: {EXECUTIVO_DIR})",
    )
    parser.add_argument(
        "--log", metavar="FILE",
        help=f"Arquivo de log (padrão: {LOG_DIR / 'downloader.log'})",
    )
    parser.add_argument(
        "--include-sundays", action="store_true",
        help="Inclui domingos ao baixar intervalos",
    )

    args = parser.parse_args()

    log_file = Path(args.log) if args.log else LOG_DIR / "downloader.log"
    _setup_logging(log_file)

    out_dir = Path(args.out) if args.out else EXECUTIVO_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    today = date.today()

    if args.date:
        d = date.fromisoformat(args.date)
        result = download_edition(d, out_dir)
        if result == "no_edition":
            logging.warning("Nenhuma edição publicada em %s.", d)
        elif result == "error":
            sys.exit(1)

    elif args.start:
        start = date.fromisoformat(args.start)
        end = date.fromisoformat(args.end) if args.end else today
        if start > end:
            parser.error("--start deve ser anterior ou igual a --end")
        summary = download_range(
            start, end, out_dir,
            skip_sundays=not args.include_sundays,
        )
        summary.log()
        if summary.error:
            sys.exit(1)

    elif args.days:
        start = today - timedelta(days=args.days - 1)
        summary = download_range(
            start, today, out_dir,
            skip_sundays=not args.include_sundays,
        )
        summary.log()
        if summary.error:
            sys.exit(1)

    else:
        # Modo padrão: tarefa agendada diária
        run_daily(out_dir)


if __name__ == "__main__":
    main()
