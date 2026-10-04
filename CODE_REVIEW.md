# Révision de Cortex Lab V0

Base examinée : 399251d299adf94b4836bb20c84affe551073795.
Cette révision corrige le laboratoire existant ; elle n'ajoute pas d'agents,
de dialogue ou de génération autonome d'objectifs.

## Défauts corrigés

1. **Perte logarithmique plafonnée.** Le produit des probabilités suivi d'un
   plancher à 1e-12 masquait les prédictions fortement erronées. Pour quatre
   bits vrais et des logits à -100, la perte retournait environ 27.63 au lieu
   de 400. Le mélange des probabilités jointes est désormais calculé par
   logsigmoid et logsumexp, directement depuis les logits. Le Brier conserve
   sa définition.
2. **Erreurs système transformées en données d'apprentissage.** Toutes les
   exceptions OSError devenaient des échecs de l'action. Une panne d'E/S ou
   un refus d'accès pouvait ainsi produire une étiquette inexpliquée par les
   trois bits observés. Seules FileNotFoundError et FileExistsError sont des
   issues attendues ; les autres erreurs remontent et interrompent le run.
3. **Dérive géométrique au déplacement nul.** Ajouter 1e-12 à la norme carrée
   rendait exp_origine(0) légèrement différent de l'origine et changeait un
   point même pour un déplacement nul. L'erreur était petite, mais violait
   les identités annoncées. Les séries en norme carrée conservent maintenant
   ces identités et des dérivées finies à zéro.
4. **Démarrage avec doublons possibles.** Les huit expériences communes
   étaient tirées avec remise. Elles couvrent maintenant deux couples
   distincts par action, avec le même démarrage pour les quatre conditions.
5. **Protocole incomplet dans les artefacts.** splits.json était omis de
   l'archive CI et écrit après l'entraînement. Il est désormais enregistré
   avant les conditions et inclus dans les artefacts. La configuration et
   le résumé identifient le protocole comme version 2.
6. **Libellé de but trompeur.** Le champ goal décrivait après coup l'action
   sélectionnée. Il devient learning_target. Le guide précise qu'aucun
   mécanisme distinct de génération d'objectifs n'est encore implémenté.

## Vérifications

La suite comprend les sept tests existants et dix tests de régression :
origine et déplacement nul exacts, gradients des petits vecteurs, norme sur
le domaine du modèle, perte de prédictions extrêmes, mélange des
distributions jointes, évaluation stable, erreurs système, démarrage et
déroulement des quatre conditions.

Le test de déroulement exécute les opérations réelles, vérifie les budgets
de mises à jour, les traces et l'exclusion des couples réservés de
l'apprentissage. Il force la branche active pour la vérifier ; le run
comparatif CI utilise ensuite le tirage aléatoire normal.

Les **17 tests passent sur Windows et Linux**. La comparaison de
200 expériences par condition, graine 0, passe aussi sur les deux systèmes.

Code vérifié : f8a0b331b415e4764c9f1e1a88ca1ffb65e48302.
[Exécution et journaux CI](https://github.com/Setharkk/Remake-setharkk/actions/runs/37164311617).

| Géométrie | Exploration | Brier final |
|---|---|---:|
| Hyperbolique | Active | 0.183795 |
| Hyperbolique | Aléatoire | 0.213789 |
| Euclidienne | Active | 0.238497 |
| Euclidienne | Aléatoire | 0.200433 |

Windows et Linux concordent à la précision présentée. Le Brier uniforme
est 0.25 ; celui de l'état inchangé avec succès à 0.5 est 0.21875 sur les
huit cas réservés de cette graine. La condition euclidienne active fait
moins bien que cette seconde référence. La sélection active fait mieux
que le hasard en hyperbolique et moins bien en euclidien sur cet essai :
aucun avantage général n'est établi.

Les changements de démarrage modifient les données observées. Ces nombres
ne permettent donc pas d'attribuer une variation de performance aux seules
corrections numériques par comparaison avec la première version.

Les archives incluent désormais splits.json :
[Windows](https://github.com/Setharkk/Remake-setharkk/actions/runs/37164311617/artifacts/11289360512)
et [Linux](https://github.com/Setharkk/Remake-setharkk/actions/runs/37164311617/artifacts/11288886558).
Ces fichiers ont la durée de conservation configurée dans GitHub Actions.

Les métriques de la première version restent dans EXPERIMENT_RESULTS.md :
elles ne constituent pas les résultats de cette version corrigée.

## Limites qui restent

Le gain d'information calcule bien l'entropie du mélange sous l'hypothèse
de bits indépendants par membre. L'ensemble de trois réseaux est cependant
une approximation heuristique, pas un posterior calibré. Cette révision
ne démontre pas que sa sélection active surpasse le hasard.

Le contrôle contient huit couples par graine, équilibrés selon la réussite.
Ses scores sont journalisés sans guider l'entraînement. Cette stratification
change la distribution mesurée et ne représente pas toute l'utilisation
possible du laboratoire.

Les poids sauvegardés permettent de restaurer les prédictions, mais ne
restaurent pas les optimiseurs et leurs états aléatoires. L'apprentissage
continu entre deux lancements reste à construire.
