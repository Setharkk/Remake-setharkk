# Revue de la V1 intrinsèque

Revue du 4 octobre 2026, sur le commit
[af6022e](https://github.com/Setharkk/Remake-setharkk/commit/af6022eb8f60e8e6113329880b107e0f60267bf2).
La revue relève trois défauts de robustesse et de validation, ainsi qu'un
écart fonctionnel connu concernant la reprise de l'apprentissage.
Les correctifs du réseau ne sont pas inclus dans cette revue.

## Défauts à corriger

### 1. [P2] Une interruption laisse les poids appris sans sauvegarde

Code : [run.py, sauvegarde après la boucle](https://github.com/Setharkk/Remake-setharkk/blob/af6022eb8f60e8e6113329880b107e0f60267bf2/cortex_lab_v1/run.py#L68).

Les poids et la mémoire ne sont écrits qu'à la fin normale de la condition.
Une erreur du système de fichiers, une interruption utilisateur ou l'arrêt
du processus pendant la boucle laisse les journaux, mais aucun instantané
du modèle de cette condition.

Reproduction : quatre interactions se terminent, puis une exception
contrôlée survient à la cinquième. Sous Windows et Linux, quatre expériences
sont journalisées, mais weights.pt et replay.json n'existent pas.
La ligne initiale des métriques est conservée. Une interaction de la V1
effectue réellement des mises à jour avant cette interruption.

Conséquence : on ne peut pas récupérer directement les poids appris pendant
la condition interrompue. Les journaux permettent éventuellement de
rejouer l'entraînement ; ils ne remplacent pas un instantané persistant.

Correction proposée : produire des instantanés périodiques, écrire dans
un fichier temporaire puis remplacer atomiquement le dernier instantané,
et prévoir une sauvegarde lors d'une interruption gérable. Un arrêt brutal
reste couvert par le dernier instantané périodique. Vérifier cette propriété
avec une erreur injectée après des interactions déjà apprises.

Ce défaut concerne la robustesse du laboratoire. Il devient prioritaire
avant toute exécution continue sur le PC.

### 2. [P2] Des entrées invalides sont converties en états/actions valides

Code : [conversion des entrées](https://github.com/Setharkk/Remake-setharkk/blob/af6022eb8f60e8e6113329880b107e0f60267bf2/cortex_lab_v1/learner.py#L35),
[indexation des prototypes](https://github.com/Setharkk/Remake-setharkk/blob/af6022eb8f60e8e6113329880b107e0f60267bf2/cortex_lab_v1/network.py#L30)
et [insertion dans la mémoire](https://github.com/Setharkk/Remake-setharkk/blob/af6022eb8f60e8e6113329880b107e0f60267bf2/cortex_lab_v1/learner.py#L46).

Les valeurs sont converties en entiers sans validation préalable.
Les indices négatifs de PyTorch sélectionnent les derniers éléments.

Reproductions exactes, sous Windows et Linux :

| Entrée invalide | Interprétation silencieuse constatée |
|---|---|
| État [-1,0,0] | Prédictions identiques à [1,0,0] |
| Action -1 | Prédictions identiques à l'action 3 |
| État [0.9,0,0] | Prédictions identiques à [0,0,0] |
| Action 1.9 | Prédictions identiques à l'action 1 |
| Résultat [1,0,0,2] | Accepté dans la mémoire et utilisé pour une mise à jour |

La fonction BCEWithLogits accepte numériquement une cible hors de [0,1] :
son absence d'erreur n'est pas une validation du résultat.
L'évaluation transforme également les cibles en booléens pour la NLL,
ce qui n'a plus la même signification qu'entraîner sur la valeur 2.

Conséquence : un appel incorrect peut produire une prédiction crédible
pour un autre état, ou contaminer l'entraînement. FileLab valide ses
propres entrées ; les candidats générés par le CLI actuel sont valides.
Le défaut se trouve dans l'API de l'apprenant et du réseau, particulièrement
avant leur branchement à d'autres sources d'observation.

Correction proposée : valider avant conversion et avant insertion.
Exiger trois bits binaires d'observation, une action entière dans [0,3],
quatre bits binaires de résultat et des valeurs finies. Une entrée invalide
doit être rejetée sans modifier la mémoire ni les paramètres.
Couvrir les indices négatifs, les fractions et les cibles invalides.

### 3. [P2] La CI V1 ignore les modifications de ses dépendances partagées

Code : [filtres de la CI V1](https://github.com/Setharkk/Remake-setharkk/blob/af6022eb8f60e8e6113329880b107e0f60267bf2/.github/workflows/cortex-intrinsic.yml#L3),
[imports de l'apprenant](https://github.com/Setharkk/Remake-setharkk/blob/af6022eb8f60e8e6113329880b107e0f60267bf2/cortex_lab_v1/learner.py#L9)
et [imports du runner](https://github.com/Setharkk/Remake-setharkk/blob/af6022eb8f60e8e6113329880b107e0f60267bf2/cortex_lab_v1/run.py#L13).

La V1 dépend de cortex_lab_v0/core.py, cortex_lab_v0/run.py et
cortex_lab_v0/file_lab.py. Son workflow ne se déclenche pourtant que
pour cortex_lab_v1/** et son propre fichier YAML.

Modifier uniquement l'une de ces trois dépendances ne déclenche aucun
test V1. Le workflow V0 exécute les tests V0 et le benchmark V0 ;
il ne couvre pas l'intégration avec l'architecture intrinsèque.

La lecture des filtres et le diagnostic de correspondance des chemins
confirment cette absence de couverture pour les trois fichiers.
Aucune modification artificielle d'une dépendance n'a été publiée pour
provoquer un échec.

Correction proposée : inclure ces dépendances dans les filtres V1,
ou déplacer les fonctions partagées dans un module commun couvert par
les workflows qui l'utilisent. Vérifier les déclencheurs et les commandes
de tests avant de considérer l'intégration protégée.

## Écart fonctionnel déjà déclaré : pas de reprise complète

Code : [contenu de checkpoint()](https://github.com/Setharkk/Remake-setharkk/blob/af6022eb8f60e8e6113329880b107e0f60267bf2/cortex_lab_v1/learner.py#L115)
et [contrat de load_weights()](https://github.com/Setharkk/Remake-setharkk/blob/af6022eb8f60e8e6113329880b107e0f60267bf2/cortex_lab_v1/learner.py#L127).

Le format actuel contient les poids, mais pas les moments de l'optimiseur,
ses compteurs, la mémoire ou les états des générateurs aléatoires.
load_weights est explicitement destiné aux poids d'inférence dans un
apprenant neuf. Cette limitation est déjà déclarée dans SPEC.md et le README ;
la reproduction ci-dessous ne montre pas une violation de ce contrat.

Reproduction : un modèle apprend pendant 40 mises à jour. On restaure
ses poids dans un modèle ayant la même graine de construction et on
reconstitue manuellement la même mémoire. Les prédictions sont identiques
avant de continuer. Après une mise à jour supplémentaire, l'écart maximal
des probabilités vaut 0.07613520505617954 sous les deux systèmes.
Le premier apprenant compte 41 mises à jour ; le restauré en compte 1.

L'exigence d'apprentissage continu demande un format distinct qui restaure
tous ces états. Un test de reprise doit comparer une exécution continue
à une exécution interrompue puis reprise, avec le même flux d'observations.

## Architecture et résultats : ce qui est établi

Les 35 tests existants passent encore sous Windows et Linux : 25 tests
partagés et 10 tests intrinsèques. Cela ne couvre pas les défauts ci-dessus.
Les jobs de diagnostic réussis indiquent que les reproductions se terminent ;
ils ne signifient pas que les défauts sont corrigés.

Les paramètres appris sont bien des points de H4 ; les couches utilisent
des distances géodésiques et des centroïdes de Lorentz ; l'optimisation
emploie un gradient riemannien, l'exponentielle et le transport des moments.
Les tests examinés sont cohérents avec cette exigence. Ils ne constituent
pas une preuve exhaustive de stabilité pour toute configuration.
Le calcul CUDA du PC de l'utilisateur n'a pas été validé.

La [validation publiée](INTRINSIC_VALIDATION.md) mesure un apprentissage
sur un laboratoire fermé de 32 couples. Sur les trois graines réservées,
la sélection active obtient un Brier final moyen de 0.200579, contre
0.179299 pour le hasard. Sa NLL se dégrade dans les trois cas.
La cause de ces résultats n'est pas établie par cette revue ;
des expériences contrôlées de calibration et de sélection restent nécessaires.

Le runner choisit des couples état/action préconstruits, et FileLab crée
un cas neuf à chaque interaction. Il n'évalue pas des séquences d'actions
dans un environnement persistant. Le dialogue, les objectifs autonomes
et le cortex coordonnant des agents restent absents, conformément à SPEC.md.

## Reproductions et données

Les [probes au commit acdded3](https://github.com/Setharkk/Remake-setharkk/blob/acdded30c84ff7cade928e3b8b03ad9729ecf1c7/review_materials/v1/probes.py)
sont exécutées sur une branche de revue qui ajoute uniquement le diagnostic
et son workflow. Le code du réseau et du laboratoire y est identique au
commit revu.

Exécution : [Intrinsic V1 review probes, 37168726957](https://github.com/Setharkk/Remake-setharkk/actions/runs/37168726957).

- [Résultats Windows](review_materials/v1/probes_windows.json)
- [Résultats Linux](review_materials/v1/probes_linux.json)

Reproduction depuis le checkout du commit de diagnostic, après installation
de cortex_lab_v1/requirements.txt :

~~~text
python -m unittest discover -s cortex_lab_v0/tests -v
python -m unittest discover -s cortex_lab_v1/tests -v
python -m review_materials.v1.probes
~~~

Les probes rapportent le comportement observé de cette version.
Elles ne sont pas des tests de régression imposant que les bugs persistent.

## Ordre de travail proposé

1. Valider les observations, actions et résultats avant leur utilisation.
2. Couvrir les dépendances partagées dans la CI.
3. Construire un état d'apprentissage complet et sa sauvegarde atomique périodique.
4. Tester la reprise exacte et l'apprentissage dans un environnement persistant.
5. Réexaminer la sélection active avec des contrôles de calibration et des références simples.

La [comparaison avec la littérature](LITERATURE_NON_EUCLIDEAN.md) explique
pourquoi un réseau hyperbolique n'est pas, à lui seul, une innovation.
