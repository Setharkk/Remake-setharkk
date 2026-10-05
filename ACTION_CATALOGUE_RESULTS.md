# Résultats : catalogue d'actions S² configurable

Les 18 cas du protocole passent tous les critères sur Windows et Linux :
4, 8 et 32 actions, trois graines, deux familles de récompenses.
Chaque cas reçoit 124 928 résultats ; cela représente 2 248 704 résultats
de recherche par plateforme, avec les mêmes graines répliquées sur les deux OS.
Les 18 tests ciblés et les comparaisons direct/service passent également.
La suite générale du code publié est vérifiée séparément avant clôture.

## Apprentissage et conservation

| Actions | Cas réussis par OS | Politique après signal, bruit, reprise et inversion | Brier pendant le bruit | Brier maximal après reprise |
|---|---:|---:|---:|---:|
| 4 | 6/6 | 100 % | 0,2576–0,2589 | 0,000024 |
| 8 | 6/6 | 100 % | 0,2566–0,2589 | 0,011628 |
| 32 | 6/6 | 100 % | 0,2570–0,2594 | 0,000024 |

Ces taux valent aussi pour les préfixes longs et le contexte non entraîné
du protocole. Aucune admission n'intervient pendant le bruit initial ou
l'interruption bruitée. Les poids sont révisés après inversion dans tous les cas.
Le Brier de la seconde moitié du bruit reste ≤0,253361.

Deux familles sont testées : toutes les actions pertinentes selon leur parité,
et une seule action correcte par état parmi N. Les actions exécutées viennent
d'une exploration aléatoire externe ; la mesure de politique choisit la
meilleure prévision sur un ensemble séparé.

La réussite finale ne signifie pas une adaptation immédiate. À 32 actions,
les cas à récompenses rares restent à 50 % au relevé de 8 192 résultats
de signal, puis atteignent 100 % à 16 384. Après inversion, les six cas
restent à 0 % au relevé de 8 192 et atteignent 100 % à 32 768.
À 8 actions, deux cas à récompenses rares sont encore à 50 % à 32 768
résultats d'inversion et atteignent 100 % à 65 536. Les courbes brutes
conservent ces délais ; les critères et durées n'ont pas été déplacés.

## Défauts reproduits et corrigés

Le premier candidat passait seulement 6 des 18 cas par plateforme.
Il pouvait figer des poids peu confiants, ne pas réviser une règle inversée,
ou conserver trop longtemps un essai dépassé. Le calibrateur dimensionné
comme les exemples par action ralentissait aussi son adaptation sous bruit.

La correction sépare la fenêtre du calibrateur scalaire des exemples neuronaux.
Elle autorise les raffinements de confiance avec confirmation future des
assertions, clôt les assertions contredites, vérifie leur actualité et
donne priorité aux inversions observées sur les raffinements d'une feuille
déjà correcte. Le risque dépensé n'est jamais remboursé. Les essais v2
importés gardent leur politique jusqu'à clôture.

| Candidat | Critères complets réussis par OS |
|---|---:|
| Initial | 6/18 |
| Assertions et calibrateur séparé | 11/18 |
| Déclencheur et essais dépassés | 11/18 |
| Contradictions et actualité | 17/18 |
| Priorité des changements de règle | 18/18 |

Les [rapports initiaux](action_results/baseline_windows.json) et le
[résumé des campagnes intermédiaires](action_results/intermediate.json)
conservent les échecs. La priorité utilise uniquement les labels passés
et les probabilités protégées ; elle ne connaît ni la phase ni la règle cachée.

## Reprise, coûts et ressources

Les 18 tests ciblés vérifient les budgets avant allocation, une banque et
une prévision à 128 actions, la sortie 31, les reprises JSON, l'isolation,
les doublons, les imports v2 d'essais et de fits en cours, les réserves
d'un arbre plein et les défauts de validation/ordonnancement reproduits.
La construction à 128 actions n'est pas une preuve d'apprentissage à 128.

Pour chaque catalogue 4/8/32 : 8 192 prévisions et checkpoints sont exacts
entre le moteur direct et son service. Partition et replay sont suspendus,
sérialisés et repris ; le quota de 128 unités est respecté, et un reçu
répété ne produit aucun gradient supplémentaire.

| Actions | Plus long advance mesuré Windows / Linux, quota 128 | Maximum de points S² échantillonné en recherche | Plus grand checkpoint JSON échantillonné |
|---|---:|---:|---:|
| 4 | 4,40 / 5,88 ms | 68 | 265 479 octets |
| 8 | 8,20 / 12,70 ms | 132 | 342 570 octets |
| 32 | 25,77 / 34,04 ms | 516 | 846 052 octets |

Ce sont des mesures CPU des runners GitHub, pas des garanties de latence
ni un benchmark de la RTX de l'utilisateur. Les tailles JSON ne sont pas
la RAM totale de Python. À 32 actions, les réserves par défaut valent
2 128 points et 53 248 lignes ; les banques retenues dans les nœuds
internes sont comptées. Les copies de checkpoint et l'exécuteur ajoutent leur coût.

## Provenance et limites

Base commune : 32a5ba2976a3955c576e9a3a0508ab92e9d44ae8.
Campagne finale : 17f609d421310ea8bd41d37dff490a0b690c44d0,
workflow [37325421414](https://github.com/Setharkk/Remake-setharkk/actions/runs/37325421414).
Les cinq fichiers du candidat mesuré sont publiés sans modification ;
les SHA de blobs et contrôles du code livré figurent dans
[source_proof.json](action_results/source_proof.json).

Rapports complets : [Windows](action_results/windows.json),
[Linux](action_results/linux.json), et campagne initiale
[Windows](action_results/baseline_windows.json) / [Linux](action_results/baseline_linux.json).
Le [protocole](ACTION_CATALOGUE_PROTOCOL.md) conserve les critères déclarés
et distingue les corrections d'algorithme des mesures.

Le catalogue reste fixe pour chaque modèle et les résultats Bernoulli.
Huit contextes, 64 symboles, huit feuilles, quatre niveaux et une action
en attente restent des limites distinctes. À grand N, la fenêtre récente
de couverture ne permet pas à toutes les actions d'atteindre simultanément
le seuil par défaut ; les comptes et leur périmètre sont annoncés explicitement.

Ces tâches ont deux états synthétiques et ne démontrent pas 32 compétences
générales indépendantes. Les résultats ne prouvent ni un catalogue infini,
ni une supériorité de S², ni le dialogue, les objectifs autonomes ou les actions PC.
