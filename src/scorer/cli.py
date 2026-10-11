"""命令列介面。

結束碼：0 全部成功；2 匯入時部分檔案失敗；1 參數或設定檔錯誤。
"""

import sys
from pathlib import Path
from typing import Annotated

import typer
from tabulate import tabulate

# Typer 0.27 起內建（vendored）Click，UsageError 未從 typer 公開匯出；版本已由 uv.lock 鎖定，
# 若升級後路徑改變，tests/test_cli.py 的結束碼測試會失敗提醒。
from typer._click.exceptions import UsageError

from scorer import db
from scorer.config import ConfigError, Segment, load_segments
from scorer.importer import import_folder
from scorer.scoring import (
    CSV_HEADER,
    format_duration,
    format_local,
    leaderboard_table_rows,
    runner_report,
    segment_leaderboard,
    write_leaderboard_csv,
)

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_PARTIAL = 2

app = typer.Typer(help="跑團區段挑戰計分工具", no_args_is_help=True, add_completion=False)

DbOption = Annotated[Path, typer.Option("--db", envvar="SCORER_DB", help="SQLite 資料庫路徑")]
ConfigOption = Annotated[Path, typer.Option("--config", envvar="SCORER_CONFIG", help="區段設定檔（YAML）")]


@app.command("import")
def import_command(
    folder: Annotated[Path, typer.Argument(exists=True, file_okay=False, help="放 GPX 檔的資料夾")],
    db_path: DbOption = Path("scorer.db"),
) -> int:
    """匯入資料夾內所有 GPX（重複內容會自動略過）。"""
    conn = db.connect(db_path)
    summary = import_folder(conn, folder)

    typer.echo("匯入摘要")
    typer.echo(f"  新增活動：{len(summary.imported)}")
    typer.echo(f"  重複略過：{len(summary.duplicates)}")
    for dup in summary.duplicates:
        # 同一檔案原樣重匯不必逐一列出；改名或換了 runner_id 才值得提醒
        if dup.name == dup.existing_file:
            continue
        warning = "（runner_id 不同，請確認是否上傳錯檔）" if dup.runner_mismatch else ""
        typer.echo(f"    - {dup.name}：與已匯入的 {dup.existing_file}（{dup.existing_runner}）內容相同{warning}")
    typer.echo(f"  失敗：{len(summary.failures)}")
    for name, reason in summary.failures:
        typer.echo(f"    - {name}：{reason}")
    return EXIT_PARTIAL if summary.failures else EXIT_OK


@app.command("leaderboard")
def leaderboard_command(
    code: Annotated[str, typer.Argument(help="區段代碼")],
    csv_path: Annotated[Path | None, typer.Option("--csv", help="另存 CSV（Excel 可直接開啟）")] = None,
    db_path: DbOption = Path("scorer.db"),
    config_path: ConfigOption = Path("segments.yaml"),
) -> int:
    """輸出區段排行榜，每位跑者只取最佳成績。"""
    segment = _find_segment(_load_config(config_path), code)
    rows = segment_leaderboard(db.connect(db_path), segment)

    typer.echo(f"{segment.code} {segment.name}｜{segment.month}｜參考長度 {segment.reference_length_m:.0f} m")
    if rows:
        typer.echo(tabulate(leaderboard_table_rows(rows), headers=CSV_HEADER, tablefmt="simple"))
    else:
        typer.echo("（尚無有效成績）")
    if csv_path is not None:
        write_leaderboard_csv(rows, csv_path)
        typer.echo(f"\n已輸出 CSV：{csv_path}")
    return EXIT_OK


@app.command("report")
def report_command(
    runner_id: Annotated[str, typer.Argument(help="跑者 ID（檔名第一個底線前的部分）")],
    db_path: DbOption = Path("scorer.db"),
    config_path: ConfigOption = Path("segments.yaml"),
) -> int:
    """列出跑者每個活動的所有嘗試，包含有效成績與無效原因。"""
    segments = _load_config(config_path)
    reports = runner_report(db.connect(db_path), runner_id, segments)
    if not reports:
        _fail(f"找不到跑者 {runner_id!r} 的任何活動")

    typer.echo(f"跑者 {runner_id}：共 {len(reports)} 個活動")
    for report in reports:
        a = report.activity
        typer.echo(
            f"\n■ {a.source_file}｜開始 {format_local(a.started_at)}｜歸屬 {a.local_month}"
            f"｜保留 {a.kept_points} 點，剔除無時間戳 {a.dropped_no_time}、飄移 {a.dropped_speed}"
        )
        if not report.attempts:
            typer.echo("  （此活動沒有任何區段嘗試）")
            continue
        table = [
            [
                segment.code,
                format_local(attempt.start_time),
                "—" if attempt.seconds is None else format_duration(attempt.seconds),
                "—" if attempt.distance_m is None else f"{attempt.distance_m:.0f} m",
                _status(segment, a.local_month, attempt.valid, attempt.reason),
            ]
            for segment, attempt in report.attempts
        ]
        typer.echo(tabulate(table, headers=["區段", "進入起點", "成績", "實際距離", "結果"], tablefmt="simple"))
    return EXIT_OK


def _status(segment: Segment, activity_month: str, valid: bool, reason: str | None) -> str:
    if not valid:
        return f"無效：{reason}"
    if activity_month != segment.month:
        return f"有效（不列入排行：挑戰月份為 {segment.month}）"
    return "有效"


def _load_config(path: Path) -> list[Segment]:
    try:
        return load_segments(path)
    except ConfigError as exc:
        _fail(f"設定檔錯誤（{path}）：{exc}")


def _find_segment(segments: list[Segment], code: str) -> Segment:
    for segment in segments:
        if segment.code == code:
            return segment
    _fail(f"設定檔中沒有區段 {code!r}，可用的區段：{', '.join(s.code for s in segments)}")


def _fail(message: str) -> None:
    typer.echo(f"錯誤：{message}", err=True)
    raise typer.Exit(EXIT_USAGE)


def main(argv: list[str] | None = None) -> int:
    """進入點。Click 預設的參數錯誤結束碼是 2，這裡改為 1 以符合規格（2 保留給部分匯入失敗）。"""
    try:
        result = app(args=argv, prog_name="scorer", standalone_mode=False)
    except UsageError as exc:
        exc.show()
        return EXIT_USAGE
    except typer.Abort:
        typer.echo("已中止", err=True)
        return EXIT_USAGE
    return result if isinstance(result, int) else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
