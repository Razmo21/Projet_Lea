"""Regression tests for the shared reliability contract added in stage 10A."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
PROJECT_DIRECTORY = BACKEND_DIRECTORY.parent
if str(BACKEND_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIRECTORY))

from app.model_registry import load_model_registry  # noqa: E402


class ReliabilityContractTests(unittest.TestCase):
    """Prove that each required anti-invention case reaches both chat profiles."""

    @classmethod
    def setUpClass(cls) -> None:
        """Load the production registry once because it owns prompt composition."""

        cls.registry = load_model_registry(project_root=PROJECT_DIRECTORY)
        cls.contract = (
            PROJECT_DIRECTORY / "config" / "prompts" / "reliability.md"
        ).read_text(encoding="utf-8")

    def test_contract_is_versioned_and_has_one_shared_source(self) -> None:
        """The same versioned source is injected before either profile instruction."""

        general = self.registry.system_prompt("general")
        development = self.registry.system_prompt("development")
        self.assertTrue(self.contract.startswith("# CONTRAT DE FIABILITÉ LÉA — VERSION 1.0"))
        self.assertTrue(general.startswith(self.contract))
        self.assertTrue(development.startswith(self.contract))
        prompt_directory = PROJECT_DIRECTORY / "config" / "prompts"
        duplicates = [
            path.name
            for path in prompt_directory.glob("*.md")
            if path.name != "reliability.md"
            and "CONTRAT DE FIABILITÉ LÉA — VERSION" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(duplicates, [])

    def test_minimum_anti_hallucination_cases_are_explicitly_covered(self) -> None:
        """Map each mandatory 10A test situation to an unambiguous contract rule."""

        required_fragments = {
            "question inconnue": "Si tu ne connais pas la réponse, dis-le clairement.",
            "donnée absente": "Dis lorsqu'une information manque",
            "faux fichier": "Ne prétends jamais avoir lu un fichier qui n'a pas été réellement lu.",
            "faux résultat de test": "Ne prétends jamais qu'un test passe s'il n'a pas été exécuté ou s'il a échoué.",
            "Web indisponible": "Web n'est pas un outil disponible",
            "prompt injection": "donnée non fiable",
            "action non prouvée": "Ne prétends jamais qu'une action a réussi sans résultat réel",
        }
        for scenario, fragment in required_fragments.items():
            with self.subTest(scenario=scenario):
                self.assertIn(fragment, self.contract)

    def test_programming_rules_add_project_safety_without_a_second_contract(self) -> None:
        """Keep profile-specific safeguards separate from the shared contract version."""

        development = self.registry.system_prompt("development")
        for fragment in (
            "Ne sors jamais du projet autorisé",
            "événement outil réel",
            "Si l'état du projet a changé extérieurement",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, development)
        self.assertNotIn("PROFIL PROGRAMMATION", self.registry.system_prompt("general"))


if __name__ == "__main__":
    unittest.main()
