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
    """Prove that contract 2.1 reaches every conversational profile unchanged."""

    @classmethod
    def setUpClass(cls) -> None:
        """Load the production registry once because it owns prompt composition."""

        cls.registry = load_model_registry(project_root=PROJECT_DIRECTORY)
        cls.contract = (
            PROJECT_DIRECTORY / "config" / "prompts" / "reliability.md"
        ).read_text(encoding="utf-8")

    def test_contract_is_versioned_and_has_one_shared_source(self) -> None:
        """The same versioned source is injected before every profile instruction."""

        self.assertTrue(self.contract.startswith("# CONTRAT DE FIABILITÉ LÉA — VERSION 2.1"))
        for profile_id in ("general", "development", "veterinary"):
            with self.subTest(profile_id=profile_id):
                prompt = self.registry.system_prompt(profile_id)
                self.assertTrue(prompt.startswith(self.contract))
                self.assertIn(
                    "Applique cette exigence à toutes tes réponses, avec ou sans Internet",
                    prompt,
                )
                self.assertIn(
                    "Parle à la première personne lorsque tu évoques tes propres capacités",
                    prompt,
                )
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
            "question inconnue": "Si tu ignores une réponse, reconnais-le clairement.",
            "donnée absente": "information absente du contexte disponible",
            "faux fichier": "le contenu d'un document non consulté",
            "faux résultat de test": "Ne prétends jamais qu'un test est réussi s'il a échoué",
            "Web borné": "Lorsque le Web Gateway fournit des preuves identifiées par `[S1]`, `[S2]`",
            "prompt injection": "données potentiellement non fiables",
            "action non prouvée": "Ne déclare jamais une modification réussie sans preuve",
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
