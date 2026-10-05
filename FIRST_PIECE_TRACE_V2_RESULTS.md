# Résultats du moteur de trace S² v2

Le [protocole préétabli](FIRST_PIECE_TRACE_V2_PROTOCOL.md) passe sur trois graines
sous Windows et Linux. Le Brier sous bruit baisse sans remplacer la compétence
protégée. Six changements successifs de règle sont appris. Le
[service optionnel](FIRST_PIECE_TRACE_V2.md) reprend le même apprentissage que le
moteur direct ; le format 8 reste le défaut.

Les mesures concernent l'expérience synthétique AAB/ABB, deux actions et quatre
contextes d'entraînement. Elles ne prouvent ni une intelligence générale, ni
une supériorité de la géométrie S².

## Résultats mesurés

Chaque graine reçoit 30 720 résultats pour bruit/signal/reprise, puis six inversions
de 32 768 résultats, soit 227 328 résultats. Les trois graines totalisent 681 984
résultats par système d'exploitation. Les prévisions sont toujours mesurées avant
le résultat utilisé pour apprendre.

| Graine | Brier v1 sous bruit après acquisition | Brier v2 | Brier v2 seconde moitié | Admissions sous bruit | Politique conservée |
|---|---:|---:|---:|---:|---:|
| 0 | 0,489663 | 0,263538 | 0,253260 | 0 | 100 % |
| 1 | 0,502986 | 0,263768 | 0,252710 | 0 | 100 % |
| 2 | 0,490652 | 0,263032 | 0,253248 | 0 | 100 % |

Ces Briers portent sur les résultats effectivement observés pendant le bruit ;
0,25 est le Brier d'une prévision constante 0,5. Le léger excès du v2 inclut le
délai de réajustement et les fluctuations de la fenêtre de calibration.

Les évaluations sans apprentissage atteignent 100 % après acquisition, après
bruit et après reprise, pour préfixes ordinaires, préfixes longs et nouveau contexte.
Après le bruit, la confiance sur une cible redevenue déterministe reste réduite :
la conservation du classement ne signifie pas que la confiance sait déjà que le
signal est revenu. Après 4 096 retours de reprise, le Brier d'évaluation revient
à environ 0,000023–0,000025. La compétence n'est pas remplacée pendant le bruit.

À 512 et 2 048 retours de signal, l'exactitude reste 50 % ; à 8 192 et 16 384, elle
est 100 %. Ces jalons montrent le temps nécessaire plutôt qu'une acquisition
instantanée.

## Changements successifs de règle

Le tableau donne le premier jalon évalué atteignant au moins 95 %. Il ne représente
pas le moment exact de l'admission. Les jalons sont 2 048, 8 192, 16 384 et 32 768.

| Graine | Inversion 1 | 2 | 3 | 4 | 5 | 6 |
|---|---:|---:|---:|---:|---:|---:|
| 0 | 16 384 | 32 768 | 32 768 | 16 384 | 16 384 | 16 384 |
| 1 | 16 384 | 16 384 | 32 768 | 32 768 | 16 384 | 16 384 |
| 2 | 16 384 | 16 384 | 32 768 | 16 384 | 16 384 | 16 384 |

Chaque inversion admet deux révisions locales, pour 12 révisions par graine.
L'exactitude finale est 100 % pour les 18 inversions ; leur Brier d'évaluation
est proche de 0,0000082. Le nombre de feuilles reste deux : réviser les poids ne
nécessite pas de subdiviser sans fin. Les compteurs de risque et de gradients
ne redémarrent pas. L'adaptation reste lente dans plusieurs cas ; réduire ce délai
sans confondre bruit et changement de règle reste un objectif de recherche.

## Vérification et coûts

Le candidat appliqué depuis ce365f306b7a1db93b4d8c7f8be0d99ca202365f a passé 174 tests sur chaque OS, dont
11 tests spécifiques à la calibration, aux révisions, aux quotas, aux pauses JSON,
aux reçus dupliqués, aux erreurs privées et aux checkpoints incohérents.

Le test long du service compare 8 192 épisodes et leurs prévisions, puis les
checkpoints toutes les 1 024 étapes : identiques au calcul direct sur chaque OS.
Il restaure des phases de moyenne et de replay. Les tests unitaires parcourent
aussi les phases de distances initiales, regroupement, support et publication,
ainsi que le replay de révision. Un reçu dupliqué ne change aucun état.
Les contrôles des sources commitées sont en cours après publication.

Pour un quota 128, le test consomme 9 781 unités en 8 204 appels. Le plus long
appel advance observé est 5,24 ms sur Linux et 8,29 ms sur Windows. Ces mesures de
runners GitHub ne sont pas une garantie de latence, et n'incluent pas les coûts
de begin_receipt, checkpoint, restore ou de sérialisation JSON.

Les relevés échantillonnés atteignent 36 points de banques/centres sur S², 1 536
lignes de replay/historique, et environ 210 ko de checkpoint JSON. Les constantes
de codage et les lignes supplémentaires des calibrations d'essais ne sont pas
des gradients ni des expériences nouvelles. Les maxima sont échantillonnés ;
ils ne constituent pas un profil de mémoire du processus.

## Reproduction et provenance

~~~text
python -m unittest discover -s first_piece/tests -v
python -m validation.trace_v2_probe --out trace-v2.json
~~~

Python 3.11 et bibliothèque standard suffisent pour ces modules.
Le workflow courant répète les tests et la comparaison coopérative sur les sources
commitées ; le protocole de recherche complet reste reproductible par la seconde
commande. Les résultats complets du candidat appliqué sont conservés dans
[Linux](trace_v2_results/linux.json) et [Windows](trace_v2_results/windows.json).
Les résultats de la première exécution complète sont également conservés.
La [preuve de sources](trace_v2_results/source_proof.json) compare les identités
Git des quatre fichiers du moteur/service appliqués en CI aux fichiers publiés.
Le fichier de tests publié durcit aussi la vérification du quota et fournit un
message complet pour le rejet d'un ancien type d'observation ; il est revérifié
sur le commit publié. Les checksums de travail ne prouvent pas l'origine historique
des données.

Les deux OS donnent les mêmes critères et conclusions. Des différences d'arrondi
dans les journaux numériques existent ; l'égalité bit à bit annoncée concerne le
calcul direct et coopératif sur un même OS.

## Limites encore ouvertes

Le backend reste borné à deux actions binaires, huit contextes, 64 symboles,
huit feuilles et profondeur quatre. Les résultats n'établissent pas sa couverture
des tâches de composition du moteur format 8. Il n'y a ni import implicite de sa
mémoire, ni fusion/suppression de feuilles, ni création de nouveaux opérateurs.

L'encodeur fixe oublie progressivement le passé lointain et peut confondre des
traces. La calibration a besoin de labels récents ; elle ne fournit pas une
incertitude épistémique sur les situations nouvelles. Les poids partagés d'une
feuille ne résolvent pas automatiquement des règles opposées entre contextes.
Une comparaison à un réseau fixe qui exploite le même état récurrent manque
encore pour attribuer le progrès à la croissance de la partition.

Les copies, les opérations administratives et la persistance sont bornées mais
pas toutes divisées en unités de travail. Le coordinateur doit encore gérer les
budgets, la persistance atomique et le journal des effets physiques. Le dialogue,
les objectifs autonomes et l'essaim d'agents restent des pièces suivantes.
