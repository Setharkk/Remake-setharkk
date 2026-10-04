# Validation du premier laboratoire

Cette exécution valide le monde séquentiel et la règle d'admission d'une
distinction fournie. **Aucun apprenant n'a été entraîné.** Les résultats
ci-dessous sont ceux d'un oracle figé qui connaît la règle et d'un
prédicteur constant.

- Source : [a76f760](https://github.com/Setharkk/Remake-setharkk/commit/a76f7603a3ff82c487890d202a51cf07dfc0df73).
- Exécution : [GitHub Actions 37196600238](https://github.com/Setharkk/Remake-setharkk/actions/runs/37196600238).
- Python 3.11, bibliothèque standard, sous Windows et Linux.
- Cinq graines : 0, 1, 2, 3, 4.
- Deux présentations : acquisition et transfert.
- Deux mondes : règle déterministe et résultats aléatoires.
- Horizons : 100, 1 000 et 10 000 interactions par condition.

## Vérifications

Les **14 tests passent sur chaque système**. Ils couvrent notamment
l'absence de la règle dans les observations publiques, les résultats
opposés pour des actions opposées, les entrées invalides sans modification
d'état, la reprise exacte du monde après sérialisation JSON, l'appariement
des observations entre les mondes structuré et aléatoire, ainsi que les
décisions du critère de validation.

Chaque audit génère 20 conditions de 10 000 interactions, soit
**200 000 interactions par système**. Les deux systèmes répètent les mêmes
graines ; leurs exécutions ne sont pas des échantillons indépendants
supplémentaires.

Les résumés JSON concordent exactement entre Windows et Linux après
exclusion du temps écoulé. Cette comparaison porte sur les métriques
enregistrées, pas sur un hachage de tous les fichiers d'observations.
Le temps écoulé comprend la génération, l'écriture et le calcul des
contrôles ; il ne mesure pas un entraînement neuronal.

## Décisions observées

Dans chaque colonne, les dix conditions correspondent aux cinq graines
et aux deux présentations. La proposition est figée avant les données.

| Interactions par condition | Monde structuré | Monde aléatoire |
|---:|---|---|
| 100 | 10 décisions en attente | 10 décisions en attente |
| 1 000 | 10 propositions acceptées | 10 propositions rejetées |
| 10 000 | 10 propositions acceptées | 10 propositions rejetées |

Le gain moyen de score logarithmique dans le monde structuré est de
0.683097 nat par interaction. La borne d'incertitude du test vaut
2.049532 à 100 interactions, 0.648119 à 1 000 et 0.204953 à 10 000.
Avec un coût de 0.01 nat, la même proposition informative passe donc de
« données insuffisantes » à « acceptée ».

L'oracle est correct sur toutes les interactions structurées. Dans les
mondes aléatoires, son exactitude à 10 000 interactions va de **48.88 % à
50.93 %**. Le critère rejette alors sa prédiction trop confiante.
Le prédicteur constant p = 0.5 a un Brier de 0.25.

Ces mesures montrent que le laboratoire contient une relation exploitable
et que le critère distingue les contrôles dans les budgets testés. Elles
ne montrent ni une découverte de règle, ni une courbe d'apprentissage.

## Données conservées

- [Résumé Windows](first_piece_results/run_37196600238/audit_windows.json).
- [Résumé Linux](first_piece_results/run_37196600238/audit_linux.json).
- Les archives de l'exécution contiennent les observations JSONL, la
  configuration, le résumé et les snapshots du monde.
- Archive Windows : identifiant 11300598236.
- Archive Linux : identifiant 11300528452.

Les archives Actions ont une durée de conservation limitée. Les résumés
et le code restent versionnés dans le dépôt.

## Limites et prochaine construction

La règle d'admission est un outil statistique standard. Elle suppose des
prédictions figées et un bloc de validation IID, avec un nombre maximal de
comparaisons annoncé. Elle ne valide pas automatiquement un apprentissage
adaptatif.

Le prochain mécanisme doit **proposer lui-même une distinction depuis son
historique**, apprendre ses prédictions et conserver ses changements.
Il faudra définir ses paramètres, sa représentation et ses opérations
non euclidiennes avant de présenter un nouveau réseau comme implémenté.

Le transfert de ce laboratoire change les longueurs d'historiques et les
distracteurs, en conservant la même règle. Aucun apprenant n'a encore subi
ce transfert. La rétention, la reprise complète d'un apprenant, les
objectifs autonomes, le dialogue et les agents restent à construire.

La [définition de la première pièce](FIRST_PIECE.md) décrit la règle candidate.
Le [protocole de mesure](MEASUREMENT_PROTOCOL.md) fixe le cadre des futures
conclusions d'apprentissage et de durée.

La [revue ultérieure de la première pièce](CODE_REVIEW_FIRST_PIECE.md)
corrige la borne à deux queues, les calculs extrêmes et la conservation
des horizons après interruption. Elle publie les 20 tests et le nouvel
audit ; les chiffres ci-dessus restent ceux de la validation initiale.
