# Premier essai de Cortex Lab V0

Code évalué : ce5f2c0f73004fa56d2c57abd0206dd9b65f0855.

[Exécution GitHub Actions](https://github.com/Setharkk/Remake-setharkk/actions/runs/37163260023).

## Protocole

- CPU, PyTorch, calculs en double précision.
- Graine 0, 200 expériences par condition.
- Trois modèles de 72 paramètres, soit 216 paramètres entraînables.
- 32 couples état/action possibles dans le laboratoire de fichiers.
- 24 couples accessibles pour l'entraînement, 8 couples réservés au contrôle.
- Un succès et un échec par action dans les couples réservés.
- Huit expériences de démarrage communes ; exploration active ensuite,
  avec 12 % d'exploration aléatoire.
- Les mises à jour utilisent uniquement les résultats des expériences
  sélectionnées, avec réutilisation de la mémoire.

## Résultats sur les huit couples réservés

Brier : moyenne des erreurs quadratiques des quatre probabilités de sortie.
Une valeur plus faible est meilleure.

| Géométrie | Exploration | Brier final |
|---|---|---:|
| Hyperbolique | Active | 0.193505 |
| Hyperbolique | Aléatoire | 0.166802 |
| Euclidienne | Active | 0.191039 |
| Euclidienne | Aléatoire | 0.177548 |

Les valeurs correspondent aux journaux Windows. Les valeurs Linux
coïncident à la précision présentée.

Les références sur ce contrôle stratifié sont :

- probabilités uniformes : 0.25 ;
- état inchangé et probabilité de succès 0.5 : 0.21875.

Les quatre conditions font mieux que ces références sur ce petit contrôle.
La sélection active fait moins bien que la sélection aléatoire pour les
deux géométries. La meilleure condition de ce seul essai est hyperbolique
avec exploration aléatoire ; cela n'établit aucune supériorité générale de
la courbure.

Le modèle améliore ici des prédictions très limitées. L'efficacité de
l'exploration active reste à démontrer. Les huit cas de contrôle et cette
seule graine ne justifient pas une conclusion sur l'autonomie générale,
la découverte de compétences nouvelles ou le contrôle d'applications.

## Validation

Les sept tests et la comparaison complète passent sur Windows et Linux :
géométrie, dérivées, budget de paramètres, gain d'information, opérations
réelles de fichiers, séparation des données, apprentissage et sauvegarde.

Le GPU et le PC de l'utilisateur n'ont pas été testés par cette CI.

Les courbes, expériences et poids sont conservés dans :

- [Artefact Windows](https://github.com/Setharkk/Remake-setharkk/actions/runs/37163260023/artifacts/11287829457)
- [Artefact Linux](https://github.com/Setharkk/Remake-setharkk/actions/runs/37163260023/artifacts/11288616885)

Ces artefacts ont la durée de conservation configurée dans GitHub Actions.

Pour répéter avec plusieurs graines :

~~~powershell
.\cortex_lab_v0\.venv\Scripts\python.exe -m cortex_lab_v0.run --steps 200 --seeds 0 1 2
~~~
