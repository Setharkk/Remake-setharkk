# Deuxième revue de Cortex Lab V0

Version examinée : 8c59f7941504a399b1cec5bd10eb7c1cf59d38f2.

La revue porte sur l'apprentissage, l'indépendance des sauvegardes,
l'initialisation aléatoire, les erreurs d'exécution et les quatre conditions
du protocole. Trois défauts de priorité P2 ont été confirmés et corrigés.

## Défauts confirmés

1. **Un instantané CPU changeait avec le réseau.**
   Dans [core.py](https://github.com/Setharkk/Remake-setharkk/blob/8c59f7941504a399b1cec5bd10eb7c1cf59d38f2/cortex_lab_v0/core.py#L244), checkpoint utilisait detach().cpu(). Sur CPU, ces opérations
   conservaient la mémoire des poids vivants. Après avoir capturé un
   instantané puis entraîné le réseau, l'instantané avait changé lui aussi.
   Modifier l'instantané modifiait inversement les prédictions du réseau.
   Chaque tenseur sauvegardé est maintenant une copie indépendante.
   Le format weights.pt reste une liste de dictionnaires de poids.

2. **L'initialisation CPU modifiait le générateur CUDA global.**
   Dans [core.py](https://github.com/Setharkk/Remake-setharkk/blob/8c59f7941504a399b1cec5bd10eb7c1cf59d38f2/cortex_lab_v0/core.py#L131), les poids étaient initialisés sur CPU
   dans fork_rng(devices=[]), mais
   torch.manual_seed réinitialise aussi les générateurs CUDA. Le contexte
   ne restaurait que le générateur CPU. L'initialisation utilise maintenant
   directement le générateur CPU. Les états CPU globaux et l'égalité des
   poids initiaux entre géométries sont vérifiés ; le test intercepte aussi
   l'appel à l'API CUDA sans nécessiter de GPU. Il ne constitue pas une
   exécution sur une RTX.

3. **Une interruption faisait perdre les métriques déjà calculées.**
   Dans [run.py](https://github.com/Setharkk/Remake-setharkk/blob/8c59f7941504a399b1cec5bd10eb7c1cf59d38f2/cortex_lab_v0/run.py#L107), metrics.csv n'était créé qu'à la fin de la condition.
   Une erreur d'E/S injectée à la cinquième expérience laissait quatre
   expériences dans le journal, mais aucune des évaluations 0, 2 et 4
   dans un CSV. Les métriques sont maintenant écrites et vidées vers le
   fichier dès chaque évaluation. L'erreur d'origine continue de remonter.
   La CI tente également d'archiver les fichiers disponibles après
   l'échec d'une comparaison commencée.

## Reproduction avant correction

Les quatre nouveaux tests ont été exécutés contre la version examinée,
sur une branche distincte. Les 17 tests précédents passaient ; les quatre
nouveaux échouaient sur Windows et Linux, conformément aux défauts décrits :
deux pour les instantanés, un pour l'initialisation et un pour les métriques.

- Commit de reproduction : eaf9615f848d39dcbf03d20b5a3a5d7b2f1304fa.
- [Journaux de reproduction](https://github.com/Setharkk/Remake-setharkk/actions/runs/37164782225).
- Tests : cortex_lab_v0/tests/test_review2.py.

L'échec de cette exécution documente les défauts de la version antérieure.

## Validation après correction

Code vérifié : 601e79cb9c3bb7c749eab656a70e1dcdbb7bc5b3.
[Exécution CI réussie](https://github.com/Setharkk/Remake-setharkk/actions/runs/37164942166).

Les **21 tests passent sur Windows et Linux**, dont les quatre nouveaux
tests qui échouaient avant correction. Le run comparatif de 200 expériences
par condition, graine 0, réussit également sur les deux systèmes.

Les quatre Brier finaux reproduisent ceux de la première revue à moins
de 1e-12 : hyperbolique actif 0.183795, hyperbolique aléatoire 0.213789,
euclidien actif 0.238497 et euclidien aléatoire 0.200433. L'apprentissage
conserve ainsi son comportement sur cet essai. L'efficacité générale de
l'exploration active reste à établir.

Les résultats et traces sont archivés :
[Windows](https://github.com/Setharkk/Remake-setharkk/actions/runs/37164942166/artifacts/11289521225)
et [Linux](https://github.com/Setharkk/Remake-setharkk/actions/runs/37164942166/artifacts/11289012379).
Leur durée de conservation dépend du réglage GitHub Actions.

Le test d'interruption vérifie la conservation du CSV après
une erreur injectée. La CI a vérifié l'archivage lors d'un run réussi ;
la nouvelle condition d'archivage après échec a été relue dans le workflow.

## Limites conservées

Cette révision ne change ni les mises à jour d'apprentissage, ni le choix
des expériences, ni le protocole version 2. Elle ne démontre pas un gain
de performance ou une autonomie générale.

Les poids et replay.json sont encore écrits en fin de condition réussie.
Préserver des métriques partielles ne permet pas de reprendre complètement
un entraînement interrompu. La reprise des optimiseurs reste à développer.

Les vérifications CPU sur Windows/Linux ne valident pas le matériel GPU
du PC de l'utilisateur.
