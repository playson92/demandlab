"""Portable command line interface for ordered DemandLab stages."""

import argparse
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description="DemandLab recorded-sales forecasting portfolio")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Project/artifact root")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, help_text in {
        "download": "Download/cache official UCI II XLSX",
        "prepare": "Clean, reconcile, select products and write daily Parquet",
        "validate": "Compare baselines and A/B/C trees on four validation origins",
        "calibrate": "Calibrate signed empirical residuals on two later windows",
        "freeze": "Save reviewed recipe and test forecasts before scoring labels",
        "test": "Score already frozen final-test forecasts",
        "demo": "Package actual aggregates and computed forecasts for offline demo",
        "report": "Generate portfolio result documentation",
        "reproduce": "Execute ordered full pipeline (independent review required before freeze)",
    }.items():
        command = subparsers.add_parser(name, help=help_text)
        if name in {"download", "prepare", "reproduce"}:
            command.add_argument("--source-file", type=Path, help="Local original XLSX")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if args.command in {"download", "prepare"}:
        from demandlab.data import download_source, prepare_data

        function = download_source if args.command == "download" else prepare_data
        function(root, args.source_file)
    elif args.command == "report":
        from demandlab.reporting import generate_report

        generate_report(root)
    else:
        from demandlab import pipeline

        functions = {
            "validate": pipeline.validate,
            "calibrate": pipeline.calibration,
            "freeze": pipeline.freeze,
            "test": pipeline.final_test,
            "demo": pipeline.build_demo,
        }
        if args.command == "reproduce":
            from demandlab.data import prepare_data
            from demandlab.reporting import generate_report

            prepare_data(root, args.source_file)
            if not (root / "reports/model_selection.json").exists():
                pipeline.validate(root)
            if not (root / "reports/calibration.json").exists():
                pipeline.calibration(root)
            pipeline.freeze(root)
            pipeline.final_test(root)
            pipeline.build_demo(root)
            generate_report(root)
        else:
            functions[args.command](root)


if __name__ == "__main__":
    main()
