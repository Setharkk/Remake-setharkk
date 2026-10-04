# Probabilités calibrées, compétence sphérique conservée

Le mode `CalibratedLearner` / `CalibratedAdapter` prolonge la
[consolidation](CONSOLIDATION.md). Il ajoute une calibration statistique
sur les résultats récents des actions exécutées. Le programme admis,
les prototypes sur S², les gradients et les admissions restent ceux
du mode consolidé.

## Pourquoi la lecture est ajustée

Une compétence protégée peut rester utile tout en prédisant mal un
monde devenu aléatoire. Le calibrateur apprend le taux de réussite
récent b par contexte et la part de contraste c encore utile dans
les probabilités brutes p. Il sert q=(1-c)b+c p.

Le [protocole](CALIBRATION_PROTOCOL.md) fixe la fenêtre, le minimum
d'exemples, l'estimation par Brier et le plancher de contraste.
Le taux b n'est pas imposé à 1/action_count. Le plancher positif
préserve l'ordre des actions à la précision disponible ; cet ordre
peut rester correct alors que les probabilités sont presque uniformes.
Il faut examiner les scores probabilistes séparément de la réussite.

La lecture brute reste accessible par
`ConsolidatedLearner.pending_probabilities(core)` pour les diagnostics.
Les déclencheurs de recherche et les gardes prospectives évaluent cette
compétence brute. Les bornes d'admission certifient son remplacement
dans leur périmètre ; elles ne certifient pas la calibration adaptative.

## Usage et reprise

Python 3.11, bibliothèque standard, même contrat version 1 et une action
en attente. La géométrie et le budget neuronal restent identiques.
Le cache de calibration ajoute au plus 256 nombres et quatre sommes
par contexte. Il réutilise les épisodes et résultats des buffers de fit.

```python
import json
from pathlib import Path
from first_piece.calibrated_adapter import CalibratedAdapter

cortex = CalibratedAdapter(actions=("left", "right"))
# Observations, propositions et reçus : SYSTEM_ARCHITECTURE.md.
Path("cortex.json").write_text(
    json.dumps(cortex.checkpoint(), ensure_ascii=False), encoding="utf-8")
cortex = CalibratedAdapter.restore(
    json.loads(Path("cortex.json").read_text(encoding="utf-8")))
```

Le cœur utilise le format 5 et l'identité
`first_piece.calibrated-compositions-s2.v1`. Le conteneur d'adaptateur
reste au format 1. Les imports sont explicites :

```python
converted = CalibratedAdapter.from_consolidated_checkpoint(old_adapter_state)
cortex = CalibratedAdapter.restore(converted)
```

Les méthodes `from_renewable_checkpoint` et `from_finite_checkpoint`
suivent d'abord les imports documentés de la consolidation.
Le format partagé 1 demande toujours sa migration historique explicite.

Une ancienne prévision en attente reste identique jusqu'à son reçu ou
sa clôture sans résultat. Ensuite, la calibration s'applique aux nouvelles
prévisions. Les reprises vérifient le cache contre les épisodes et les
poids protégés, puis les sommes contre les résultats. Le reçu répété
ne met à jour ni le réseau ni les statistiques une deuxième fois.
Les copies transactionnelles isolent aussi ce cache.

Lors d'une admission, les probabilités des lignes récentes sont
recalculées depuis les nouvelles routes et poids. Cette projection
consomme des calculs supplémentaires, sans gradient neuronal ni donnée
future. L'ajustement du passé n'est pas une mesure de performance future.

Les capacités annoncent la calibration et sa fenêtre ; les métriques
publient les paramètres par contexte, le nombre de probabilités en cache
et la référence brute des validations. La confiance épistémique reste
non estimée. Il s'agit de calibration des prévisions Bernoulli.

```powershell
python -m unittest discover -s first_piece/tests -v
python -m validation.calibration_probe --out results/calibration.json
```

## Limites

Les résultats concernent des actions exploratoires uniformes, des
frontières d'épisode fournies et une famille de prédicats limitée.
Une autre sélection d'actions peut changer la signification du taux
récent b ; aucune correction par propension n'est fournie.
La fenêtre impose une inertie mesurable aux transitions et peut
perdre des différences entre sous-régions d'un même contexte.
La calibration ne crée ni nouvelle règle, ni objectif, ni dialogue.

Cette statistique est un mécanisme connu. Elle ne constitue pas un
nouveau réseau euclidien, une innovation scientifique démontrée ou une
preuve de supériorité de la courbure. Le réseau neuronal reste S².
Le coordinateur, les agents autonomes et les applications PC restent
à construire.
