# Première pièce : compétence protégée et validation prolongée

Le mode `ConsolidatedLearner` / `ConsolidatedAdapter` ajoute une compétence
protégée au [mode renouvelable](RENEWABLE_SEARCH.md). Il reste un laboratoire
synthétique de prédicats bornés et de prototypes neuronaux S².

## Réseau et apprentissage

Une banque active et un contrôle reçoivent toujours des gradients à chaque retour.
Les banques proposées sont ajustées puis figées avant les données de validation.
Après admission, une copie de la banque proposée devient la compétence protégée
et sert les prévisions structurées. Elle n'est plus modifiée par les gradients
intermédiaires. Une nouvelle admission remplace sa banque et son programme.

Ce découplage conserve la dernière compétence admise ; ce n'est pas un stockage
illimité de toutes les règles antérieures. Les poids de travail apprennent pendant
les interactions, tandis que les prévisions consolidées évoluent lors des admissions.
La qualité des probabilités pendant un monde aléatoire doit être mesurée séparément
de la conservation d'une règle structurée.

Tous les paramètres neuronaux restent des points sur S². La copie ajoute
32 points avec quatre actions et huit routes : après admission, 96 points en service
avec banques de travail et contrôle, 160 avec candidats. Cela représente
192/320 degrés de liberté intrinsèques. Les états discrets, buffers et journaux
sont comptés séparément ; leur taille reste bornée.

## Validation et risque

Les nouveaux essais déclarent les horizons 128, 1 024, 4 096, 8 192, 16 384
retours principaux. La clôture inconclusive intervient seulement au dernier.
Une expiration sans progrès continue de compter des retours appris globaux ;
elle ne crée pas un nouveau regard et ne rembourse pas une tentative.

Les réseaux de conservation sont figés. Le modèle fixe avant validation une
largeur conditionnelle maximale sur toutes les actions et routes possibles des
autres contextes, puis utilise cette largeur dans la borne uniforme dans le temps.
Les comparaisons avec une banque plastique conservent la largeur universelle.
Le [protocole mathématique](CONSOLIDATION_PROTOCOL.md) donne les formules,
l'énumération conservatrice des routes et les conditions de validité.

Le risque des nouveaux essais est réparti sur cinq regards. Le budget de chaque
tentative reste inclus dans le budget de son bloc ; les blocs gardent leur somme
à vie. La frontière de politique conserve les trois horizons et anciennes bornes
des tentatives déjà commencées avant l'import. Il n'y a pas de remboursement
d'essai ni de réécriture des décisions historiques.

Le journal détaillé garde au plus un bloc de 16 recherches et 80 décisions par
défaut. Le résumé du préfixe compte toujours les essais, ajustements, admissions,
clôtures et dernière admission. La banque protégée est unique. Le journal n'est
ni une archive intégrale des résultats passés ni une preuve cryptographique.

## Interfaces et reprise Windows

Python 3.11 et la bibliothèque standard suffisent. Même contrat version 1,
observations ordonnées, candidats évalués et une requête en attente.

```python
import json
from pathlib import Path
from first_piece.consolidated_adapter import ConsolidatedAdapter

cortex = ConsolidatedAdapter(
    actions=("action.a", "action.b", "action.c", "action.d"))
# Envoyer les observations, choisir une proposition et livrer son reçu
# selon SYSTEM_ARCHITECTURE.md.
Path("cortex.json").write_text(
    json.dumps(cortex.checkpoint(), ensure_ascii=False), encoding="utf-8")
cortex = ConsolidatedAdapter.restore(
    json.loads(Path("cortex.json").read_text(encoding="utf-8")))
```

Le cœur écrit le format 4, identité
`first_piece.consolidated-compositions-s2.v1`. Le conteneur d'adaptateur reste
au format 1. Les copies transactionnelles détachent aussi la banque protégée.

Import explicite depuis le format 3 renouvelable :

```python
converted = ConsolidatedAdapter.from_renewable_checkpoint(old_adapter_state)
cortex = ConsolidatedAdapter.restore(converted)
```

Pour le cœur seul, utiliser `ConsolidatedLearner.from_renewable_checkpoint`.
Un état partagé format 2 utilise `from_finite_checkpoint` ; le format 1 doit
d'abord suivre la migration publiée dans [CURRENT_FIXES.md](CURRENT_FIXES.md).

L'import capture les poids actifs présents, pas des poids historiques perdus.
Les compteurs, essais, risques, RNG, observations, validation et requête en cours
sont conservés. Une validation antérieure conserve ses anciens horizons.
La prédiction en attente reste identique ; son reçu n'est appris qu'une fois.
Un import depuis un modèle renouvelable neuf conserve la borne à vie 0,05 ;
depuis le modèle fini historique, la borne conservatrice reste 0,10.

L'appelant doit sauvegarder un état cohérent avec son journal durable pour la
reprise après panne. Cette bibliothèque ne fournit pas le journal d'exécution PC.

Les capacités annoncent le mode consolidé, une banque protégée et les horizons
de la politique de la tentative courante (ou dernière), qui peut être historique
après import. Les nouveaux essais du mode déclarent les cinq horizons ci-dessus.
Les métriques distinguent la banque servie, la capture protégée, les compteurs
d'apprentissage, le risque et les points effectivement alloués.

```powershell
git clone https://github.com/Setharkk/Remake-setharkk.git
cd Remake-setharkk
python -m unittest discover -s first_piece/tests -v
python -m validation.consolidation_probe --out results/consolidation.json
```

Les [résultats complets](CONSOLIDATION_RESULTS.md) donnent les courbes, délais,
coûts et régressions de calibration observées sur les trois graines.

## Limites

La copie protège une compétence ; elle ne choisit pas seule les buts d'un cortex.
Les observations, familles de prédicats et frontières d'épisode sont fournies.
Les limites configurées restent trois prédicats, 128 symboles, 32 contextes
et seize actions. Une compétence protégée peut être mal calibrée sous bruit ;
sa préservation n'est pas une garantie de performance dans tout environnement.

Les horizons sont prolongés mais encore bornés. Le risque décroissant peut
toujours empêcher une admission faible, et les changements très rapides peuvent
arriver avant une décision. Le ralentissement du pas des banques de travail
avec l'âge reste inchangé. Aucun avantage sur une capacité euclidienne équivalente
ni innovation scientifique n'est démontré. Dialogue, objectifs autonomes,
essaim et exécuteur PC restent à construire.
