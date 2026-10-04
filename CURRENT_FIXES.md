# Corrections de la première pièce — 4 octobre 2026

Ce rapport conserve les corrections du moteur historique à budget fini. Les évolutions suivantes sont documentées dans le [mode renouvelable](RENEWABLE_SEARCH.md), puis le [mode consolidé](CONSOLIDATION.md) et ses [mesures](CONSOLIDATION_RESULTS.md).

> Suite de ce rapport historique : le [mode renouvelable](RENEWABLE_SEARCH.md) est livré avec [mesures de longue durée](RENEWABLE_SEARCH_RESULTS.md) et 104 tests. Le moteur fini, ses six corrections et sa migration format 2 restent conservés.

Les six familles de défauts de la [revue](CODE_REVIEW_CURRENT.md) sont corrigées à la source [99cf3b3](https://github.com/Setharkk/Remake-setharkk/commit/99cf3b33d78f77ea7a17fa1c74eaf0ee629e2204). Les **97 tests passent sous Windows et Linux**, et les reproductions avant/après vérifient l’apprentissage par défaut, la clôture des validations bloquées, les scores servis et la reprise.

Le réseau conserve ses points S², sa lecture géodésique et ses gradients riemanniens. Ces corrections réparent son fonctionnement ; elles ne démontrent pas une nouvelle théorie de l’IA.

## Résultats avant/après

Même fixture, mêmes budgets d’entraînement et mêmes tirages réservés pour l’évaluation. La version précédente est chargée depuis son commit original dans un module isolé ; la correction ne simule pas ses défauts.

| Défaut | Avant | Après |
|---|---|---|
| F1, contexte unique par défaut | Aucune tentative après 20 000 retours ; 24,02 % de réussite sur 512 épisodes | Une tentative et une admission ; **100 %** sur les 512 épisodes |
| F2, contexte principal absent | Validation encore ouverte après 5 000 autres retours | Clôture après **4 096 retours sans progrès**, sans admission ni remboursement d’essai |
| F3, mode sans structure partagé | Écart de probabilité maximal 0,793 ; de Brier 0,631 | **Écarts nuls** sur les 32 interactions comparées |
| F3, référence temporelle | Écart de Brier maximal 0,493 | **Écart nul** sur les 32 interactions comparées |
| F4, reprise incohérente | Compteurs inégaux, journal impossible et dernier symbole absent acceptés | Trois contradictions **refusées**, état authentique restaurable |
| F5, point antipodal | Reprise acceptée, apprentissage échoue ensuite | État **refusé à la restauration** ; voisins réguliers testés |
| F6, graine trop grande | Construction autorisée puis reprise refusée | Refus dès la construction ; graine maximale autorisée restaurable |

Les données sont des contre-exemples et leurs corrections à graines fixes, pas un taux général de panne ou une mesure d’intelligence. Le budget de 20 000 retours n’est pas une durée universelle d’acquisition.

## Changements du moteur

### Collecte atteignable

`min_records` est désormais une **cible d’ajustement**, limitée par les buffers des contextes qui ont réellement reçu des labels. Avec un seul contexte, les 256 records disponibles suffisent à proposer une relation, tout en conservant les seuils de support et d’admission.

Un contexte très brièvement alimenté puis abandonné ne doit pas rendre cette cible inaccessible. Après le warmup global, si un buffer est plein, le moteur peut ajuster avec les records effectivement conservés. Un test couvre un contexte avec un seul retour suivi de 511 retours de l’autre contexte. Les contextes vus uniquement en évaluation ne gonflent pas la cible.

Les métriques exposent `required_fit_records` et `fit_wait_reason`. Les premières propositions dans les benchmarks équilibrés à plusieurs contextes restent à leur cible de 512 records.

### Cycle de vie des validations

`trial_stall_limit=4096` borne le nombre de **retours appris globaux consécutifs sans retour du contexte principal**. Chaque progrès de celui-ci rafraîchit la frontière d’attente. Une validation globale progresse à chaque label.

À expiration, le moteur journalise `expired`, libère candidat et contrôle et applique son cooldown. Il ne produit pas d’intervalle statistique à un horizon improvisé et ne restitue pas la tentative consommée. Les poids en service continuent d’apprendre.

Le compteur d’attente survit à la reprise ; la sonde restaure après 3 000 retours complémentaires et retrouve exactement la même clôture à 4 096. Un autre test vérifie que la recherche peut redémarrer si un autre contexte présente une erreur suffisante.

Cette borne mesure des interactions, pas des secondes. Si aucun retour n’arrive, l’attente ne progresse pas ; un futur coordinateur devra gérer les délais d’exécution et les événements sans résultat. Un contexte très rare peut expirer avant d’avoir assez d’exemples : configurer son budget et son ordonnancement explicitement.

### Scores et domaine numérique

Le Brier, le gain contre le modèle servi et la valeur renvoyée par `SharedLearner.learn` utilisent désormais la probabilité réellement servie **avant** le retour, dans les deux modes de lecture. L’entraînement des deux banques reste distinct de ce score. La référence temporelle reçoit la même correction.

La restauration vérifie que les logarithmes requis par chaque point sont définis dans le domaine numérique du noyau sphérique. Elle refuse les antipodes au lieu d’inventer une direction. Aucun réseau ou poids euclidien n’est ajouté.

Les graines partagées sont bornées à 2⁵³−1 dès la construction, comme les autres compteurs JSON.

### Invariants croisés de reprise

Le nouvel état contrôle les champs, types, horizons et chronologies des recherches et décisions, leur correspondance au candidat courant, les supports de routes et l’application des budgets d’intervalles. Il vérifie le nombre total de mises à jour depuis les labels et les ajustements, ainsi que les compteurs des banques en service depuis la dernière admission.

L’adaptateur vérifie que le dernier symbole consommé appartient au vocabulaire et à la mémoire active. Les objets publics restent détachés et les refus de transaction conservent l’état précédent.

Ces contrôles détectent des contradictions avec l’état conservé. Ils ne constituent pas une preuve d’intégrité cryptographique ni une garantie d’absence de tout autre bug.

## Checkpoints et migration explicite

Le cœur partagé écrit désormais le **format 2**. Les contrats de messages et le format extérieur de l’adaptateur restent en version 1 : les séquences, prédictions, propositions et reçus conservent leur structure.

Une restauration directe de l’ancien format est refusée avec une instruction de migration :

```python
from first_piece.shared import SharedLearner
from first_piece.shared_adapter import SharedAdapter

# Pour un ancien état du cœur :
core = SharedLearner.restore(
    SharedLearner.migrate_checkpoint_v1(old_core_snapshot)
)

# Pour un ancien checkpoint de l’adaptateur :
adapter = SharedAdapter.restore(
    SharedAdapter.migrate_checkpoint_v1(old_adapter_snapshot)
)
```

La migration valide puis conserve les poids en service, RNG, vocabulaire, données, admissions, tentatives et nombre total de mises à jour. Elle conserve une prédiction et une requête d’action en attente, ainsi que leur cache de reçus. Le test livre le même reçu deux fois et constate un seul apprentissage.

Les anciennes validations encore ouvertes sont **clôturées sans admission**, car leur dernière frontière de progrès n’a pas été enregistrée. La clôture est journalisée `migrated` et conserve l’essai consommé. Leur candidat ne devient pas un modèle admis. Les validations historiques restent identifiées `legacy_active` ; en ancien mode sans structure, leurs scores ne deviennent pas rétroactivement des scores servis, et leurs fenêtres d’erreur sont vidées.

Les frontières d’épisode et d’action sont conservées ; le monde et le journal d’exécution externe doivent être restaurés séparément par leur propriétaire. L’adaptateur ne garantit toujours pas une exécution physique unique après une panne du PC.

## Vérification et preuves

- [Corrections, 97 tests et migration](https://github.com/Setharkk/Remake-setharkk/actions/runs/37220417809), [sonde avant/après](validation/current_fix_probe.py), [tests de régression](first_piece/tests/test_current_fixes.py).
- [Données Windows](first_piece_current_fixes/windows.json), [Linux](first_piece_current_fixes/linux.json), [comparaison](first_piece_current_fixes/comparison.json).
- [Montée à l’échelle de la source corrigée](https://github.com/Setharkk/Remake-setharkk/actions/runs/37220417831).
- [Laboratoire historique et intégration](https://github.com/Setharkk/Remake-setharkk/actions/runs/37220417795).
- [Compatibilité des anciens états figés et holdout](https://github.com/Setharkk/Remake-setharkk/actions/runs/37220417903).

Le workflow de montée à l’échelle suit maintenant aussi le module de validation d’état, ses tests et les contrats ; leurs modifications ne peuvent plus éviter cette expérience.

La comparaison avant/après vérifie 65 valeurs numériques et ne trouve aucun écart de résultat catégoriel ; écart numérique maximal **3,33×10⁻¹⁶**.

Le benchmark corrigé reçoit **1 560 000 retours et 3 602 968 mises à jour neuronales par système**. Il couvre les trois échelles, trois graines et dix mille retours par contexte avant et après changement. Ses 54 groupes finaux, 55 296 épisodes sans entraînement, atteignent 100 % dans cette famille synthétique, avec parité du cœur et de l’interface. Les **10 434 valeurs numériques** comparées entre systèmes diffèrent au maximum de **2,66×10⁻¹⁵**, hors temps et tailles JSON. Les [rapports Windows](first_piece_current_fixes/scale_windows.json) et [Linux](first_piece_current_fixes/scale_linux.json) contiennent aussi les horizons courts et les régressions transitoires.

La validation des **18 anciens états figés** utilise une migration explicite du format 1 ; ses 54 groupes et 55 296 épisodes par système restent à 100 %. Elle évalue les anciens poids conservés, et ne constitue pas un nouvel entraînement de ces états. Les contrôles de bruit ajoutent séparément 60 000 retours par système et n’admettent aucune structure : [Windows](first_piece_current_fixes/frozen_windows.json), [Linux](first_piece_current_fixes/frozen_linux.json).

Les références de présence et d’ordre, la sonde d’intégration et le laboratoire d’évidence passent aussi. Les artifacts des workflows contiennent les états complets. Les temps proviennent des runners GitHub, Python CPU ; aucune mesure sur la RTX de l’utilisateur n’est revendiquée.

Pour rejouer les corrections :

```text
python -m unittest discover -s first_piece/tests -v
python -m validation.current_fix_probe --out current-fixes.json
```

La sonde a besoin de l’historique Git des sources indiquées ; les workflows utilisent un checkout complet.

## Limites toujours présentes

Les seize tentatives restent un budget global **non renouvelable**. L’expiration et la migration ne le remettent pas à zéro. Les contrôles de bruit consomment encore seize essais sans admission : le renouvellement doit gérer le risque statistique sur toute la durée de vie, avec une reprise et un journal cohérents.

Le pas diminue encore avec l’âge du neurone. La mémoire ignore les comptages de répétitions, la recherche reste bornée à trois prédicats, et la garde compare une compétence courante plutôt qu’un niveau historique conservé. L’avantage de S² sur une version euclidienne de même capacité reste non mesuré.

Le dialogue, les objectifs autonomes, l’ordonnancement d’agents et les actions sur les applications du PC restent à construire. La prochaine expérience de la première pièce doit traiter le renouvellement de recherche et la rétention longue, puis raccorder un coordinateur minimal sur ces états et ces unités explicites.

