# Première pièce : apprenant à mémoire d'événements

La [définition](../FIRST_PIECE.md) décrit maintenant l'apprenant :
mémoire de présence alimentée événement par événement, prototypes
neuronaux sur S², proposition d'une distinction depuis le passé et
validation contre un contrôle ajusté à budget égal.

Les [résultats mesurés](../FIRST_PIECE_LEARNING_RESULTS.md) donnent les
courbes, le transfert, la rétention, le bruit et la reprise.

Python 3.11, bibliothèque standard uniquement :

~~~text
python -m unittest discover -s first_piece/tests -v
python -m first_piece.learning_run --seeds 0 1 2 3 4 --out first_piece/lab_runs/apprentissage_1
~~~

Les horizons d'apprentissage sont 100, 1 000 et 10 000 interactions.
Les checkpoints conservent l'apprenant complet, le monde et les mesures.
Le chemin de sortie doit être neuf.

Le laboratoire historique sans apprenant reste accessible :

~~~text
python -m first_piece.audit --out first_piece/lab_runs/audit_1
python -m first_piece.review_probe --out revue-premiere-piece.json
~~~

Le premier utilise un oracle pour contrôler le monde, et non pour
entraîner l'apprenant. Le second rejoue la revue avant/après depuis Git
et nécessite l'historique complet du dépôt.

La découverte reste limitée à une présence de symbole par tâche.
La courbure est fixée et le contrôle porte sur cette petite architecture.

## Interface commune du système

L'[architecture](../SYSTEM_ARCHITECTURE.md) précise les responsabilités du
cortex, des agents et de l'exécuteur. `FirstPieceAdapter` conserve
l'apprenant central et expose des messages versionnés ; les agents n'ont
pas à connaître ses tâches locales, masques ou coordonnées sphériques.

~~~text
python -m first_piece.integration_probe --out integration.json
~~~

Cette sonde vérifie deux agents simulés sur le même contexte, la parité
avec le modèle direct, la reprise avec une action en attente et
l'absence d'apprentissage supplémentaire lors d'un résultat répété.
Elle n'agit sur aucune application du PC.

La [prochaine expérience](../FIRST_PIECE_NEXT_PROTOCOL.md), encore à
implémenter, doit apprendre l'ordre puis une règle modifiée dans le même
contexte. Un checkpoint de présence ne permet pas de reconstruire l'ordre
qu'il n'avait pas enregistré : la migration devra être explicite.
