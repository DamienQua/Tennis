"""Calculateur de complexité cyclomatique aligné sur Scrutinizer CI pour Python."""

import ast
import os
import sys
from typing import Dict, List, Set, Tuple

BRANCH_TYPES = (
    ast.If,
    ast.IfExp,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.With,
    ast.AsyncWith,
    ast.ExceptHandler,
    ast.Assert,
)


class ScrutinizerComplexityVisitor(ast.NodeVisitor):
    """Calcule la complexité cyclomatique (McCabe) selon les règles Scrutinizer CI."""

    def __init__(self) -> None:
        self.functions: Dict[str, int] = {}
        self.current_class: List[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.current_class.append(node.name)
        self.generic_visit(node)
        self.current_class.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._process_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._process_function(node)

    def _process_function(self, func_node) -> None:
        class_prefix = f"{'.'.join(self.current_class)}." if self.current_class else ""
        func_name = f"{class_prefix}{func_node.name}"
        self.functions[func_name] = self._calculate_complexity(func_node)
        for item in func_node.body:
            if isinstance(item, ast.ClassDef):
                self.visit(item)

    @staticmethod
    def _extract_excluded_ids(func_node) -> Set[int]:
        excluded: Set[int] = set()
        for node in ast.walk(func_node):
            if isinstance(node, ast.IfExp):
                for child in ast.walk(node.test):
                    excluded.add(id(child))
            elif isinstance(node, ast.Return) and node.value:
                for child in ast.walk(node.value):
                    excluded.add(id(child))
        return excluded

    def _calculate_complexity(self, func_node) -> int:
        complexity = 1
        excluded_ids = self._extract_excluded_ids(func_node)
        for node in ast.walk(func_node):
            if node is func_node:
                continue
            if isinstance(node, BRANCH_TYPES):
                complexity += 1
            elif isinstance(node, ast.comprehension):
                complexity += 1 + len(node.ifs)
            elif isinstance(node, ast.BoolOp) and id(node) not in excluded_ids:
                complexity += len(node.values) - 1
        return complexity


def analyze_file(filepath: str) -> Dict[str, int]:
    """Analyse un fichier Python et retourne la complexité par fonction."""
    try:
        with open(filepath, "r", encoding="utf-8") as file:
            content = file.read()
        tree = ast.parse(content)
        analyzer = ScrutinizerComplexityVisitor()
        analyzer.visit(tree)
        return analyzer.functions
    except (SyntaxError, UnicodeDecodeError, OSError) as err:
        print(f"Erreur lors de l'analyse de {filepath}: {err}")
        return {}


def find_python_files(directory: str = ".") -> List[str]:
    """Trouve tous les fichiers Python du répertoire."""
    python_files: List[str] = []
    ignored = {".git", ".vscode", "__pycache__", "venv", "env", "node_modules"}
    for root, dirs, files in os.walk(directory):
        dirs[:] = [
            dir_name
            for dir_name in dirs
            if not dir_name.startswith(".") and dir_name not in ignored
        ]
        for file in files:
            if file.endswith(".py"):
                python_files.append(os.path.join(root, file))
    return python_files


def get_scrutinizer_grade(complexity: int) -> Tuple[str, str]:
    """Retourne la note Scrutinizer CI (A, B, C, D, F) et son badge."""
    if complexity <= 5:
        return "A", "A (Faible)"
    if complexity <= 8:
        return "B", "B (Bonne)"
    if complexity <= 10:
        return "C", "C (Modérée)"
    if complexity <= 20:
        return "D", "D (Élevée)"
    return "F", "F (Critique)"


def print_results_table(all_results: Dict[str, Dict[str, int]]) -> None:
    print("TABLEAU DE COMPLEXITÉ CYCLOMATIQUE (Scrutinizer CI)")
    print("=" * 95)
    print(f"{'Fichier':<38} {'Fonction / Méthode':<38} {'CC':<5} {'Grade':<14}")
    print("-" * 95)
    for filepath, functions in all_results.items():
        file_displayed = False
        for func_name, complexity in sorted(functions.items(), key=lambda x: x[1], reverse=True):
            _, badge = get_scrutinizer_grade(complexity)
            file_display = filepath if not file_displayed else ""
            print(f"{file_display:<38} {func_name:<38} {complexity:<5} {badge}")
            file_displayed = True
        print("-" * 95)


def main() -> int:
    """Exécute l'audit de complexité et retourne 1 si une fonction dépasse CC=10."""
    python_files = find_python_files()
    if not python_files:
        print("Aucun fichier Python trouvé.")
        return 0

    all_results = {
        fp: funcs for fp in sorted(python_files) if (funcs := analyze_file(fp))
    }
    if not all_results:
        print("Aucune fonction trouvée.")
        return 0

    print_results_table(all_results)
    all_cc = [cc for funcs in all_results.values() for cc in funcs.values()]
    print(f"\nFonctions analysées : {len(all_cc)} | Moyenne CC : {sum(all_cc)/len(all_cc):.2f} | Max CC : {max(all_cc)}")
    return 1 if max(all_cc) > 10 else 0


if __name__ == "__main__":
    sys.exit(main())