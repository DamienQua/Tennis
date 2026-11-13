BEGIN TRANSACTION;
CREATE TABLE bets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    match_url TEXT UNIQUE NOT NULL,
                    detected_at TEXT NOT NULL,
                    tournament TEXT,
                    surface TEXT,
                    player_a TEXT,
                    player_b TEXT,
                    selected_player TEXT,
                    book_odds REAL,
                    model_odds REAL,
                    model_prob REAL,
                    ev_percent REAL,
                    elo_diff REAL,
                    kelly_stake_pct REAL DEFAULT 0.0,
                    status TEXT DEFAULT 'En attente',
                    winner TEXT DEFAULT '',
                    profit_units REAL DEFAULT 0.0
                , closing_odds REAL DEFAULT 0.0, clv_percent REAL DEFAULT 0.0);
INSERT INTO "bets" VALUES(1,'https://tennisinsight.com/match/260564112/2026-indian-wells-wta-champs/rr/aryna-sabalenka-vs-elina-svitolina','13/11/2026 11:41','Indian Wells WTA Champs','Hard','Aryna Sabalenka','Elina Svitolina','Aryna Sabalenka',1.51,1.23,7.33766233766233733e-01,10.8,1.70600000000000136e+02,3.0,'En attente','',0.0,1.48,2.03);
CREATE TABLE matches (
                    match_url TEXT PRIMARY KEY,
                    analyzed_at TEXT NOT NULL,
                    tournament TEXT,
                    surface TEXT,
                    player_a TEXT,
                    player_b TEXT,
                    model_odds_a REAL,
                    model_odds_b REAL,
                    book_odds_a REAL,
                    book_odds_b REAL,
                    elo_a REAL,
                    elo_b REAL,
                    confidence_index REAL,
                    summary_line TEXT
                );
INSERT INTO "matches" VALUES('https://tennisinsight.com/match/260564112/2026-indian-wells-wta-champs/rr/aryna-sabalenka-vs-elina-svitolina','2026-11-13T11:41:33','Indian Wells WTA Champs','Hard','Aryna Sabalenka','Elina Svitolina',1.23,3.39,1.51,2.6,2136.8,1966.2,3.0,'Indian Wells WTA Champs, Hard, Aryna Sabalenka, Elina Svitolina, 1.23, 3.39, 1.51, 2.6, 2136.8, 1966.2, 76.0, 66.0, 3.0, 73.98, 67.75');
INSERT INTO "matches" VALUES('https://tennisinsight.com/match/260644402/2026-sopo-wta-ch/sf/laura-samson-vs-elizabeth-mandlik','2026-11-13T11:43:54','Sopo WTA Ch','Clay','Laura Samson','Elizabeth Mandlik',0.99,9.54,1.43,2.7,1628.5,1458.1,3.0,'Sopo WTA Ch, Clay, Laura Samson, Elizabeth Mandlik, 0.99, 9.54, 1.43, 2.7, 1628.5, 1458.1, 64.0, 54.0, 3.0, 71.62, 51.45');
INSERT INTO "matches" VALUES('https://tennisinsight.com/match/260554401/2026-stockholm-atp-250/sf/taylor-fritz-vs-lorenzo-musetti','2026-11-13T11:44:01','Stockholm ATP 250','Indoor Hard','Taylor Fritz','Lorenzo Musetti',1.6,2.05,1.58,2.3,1899.6,1850.5,3.0,'Stockholm ATP 250, Indoor Hard, Taylor Fritz, Lorenzo Musetti, 1.6, 2.05, 1.58, 2.3, 1899.6, 1850.5, 70.0, 66.0, 3.0, 60.0, 53.19');
INSERT INTO "matches" VALUES('https://tennisinsight.com/match/260564111/2026-indian-wells-wta-champs/rr/mirra-andreeva-vs-karolina-muchova','2026-11-13T11:44:25','Indian Wells WTA Champs','Hard','Mirra Andreeva','Karolina Muchova',1.07,5.79,1.34,3.3,1982.0,1935.7,3.0,'Indian Wells WTA Champs, Hard, Mirra Andreeva, Karolina Muchova, 1.07, 5.79, 1.34, 3.3, 1982.0, 1935.7, 78.0, 74.0, 3.0, 73.08, 68.64');
INSERT INTO "matches" VALUES('https://tennisinsight.com/match/260644401/2026-sopo-wta-ch/sf/polona-hercog-vs-bianca-andreescu','2026-11-13T11:44:31','Sopo WTA Ch','Clay','Polona Hercog','Bianca Andreescu',9.9,0.99,3.6,1.27,1510.8,1725.0,1.0,'Sopo WTA Ch, Clay, Polona Hercog, Bianca Andreescu, 9.9, 0.99, 3.6, 1.27, 1510.8, 1725.0, 54.0, 68.0, 1.0, 0.0, 65.48');
INSERT INTO "matches" VALUES('https://tennisinsight.com/match/260554402/2026-stockholm-atp-250/sf/alejandro-tabilo-vs-thiago-agustin-tirante','2026-11-13T11:51:02','Stockholm ATP 250','Indoor Hard','Alejandro Tabilo','Thiago Agustin Tirante',1.8,1.8,1.69,2.29,1731.8,1669.4,1.0,'Stockholm ATP 250, Indoor Hard, Alejandro Tabilo, Thiago Agustin Tirante, 1.8, 1.8, 1.69, 2.29, 1731.8, 1669.4, 52.0, 58.0, 1.0, 37.04, 45.0');
INSERT INTO "matches" VALUES('https://tennisinsight.com/match/260564108/2026-indian-wells-wta-champs/rr/aryna-sabalenka-vs-mirra-andreeva','2026-11-13T11:55:50','Indian Wells WTA Champs','Hard','Aryna Sabalenka','Mirra Andreeva',1.32,2.84,1.91,1.94,2136.8,1982.0,2.0,'Indian Wells WTA Champs, Hard, Aryna Sabalenka, Mirra Andreeva, 1.32, 2.84, 1.91, 1.94, 2136.8, 1982.0, 78.0, 78.0, 2.0, 74.15, 72.87');
INSERT INTO "matches" VALUES('https://tennisinsight.com/match/260564107/2026-indian-wells-wta-champs/rr/elina-svitolina-vs-karolina-muchova','2026-11-13T11:55:50','Indian Wells WTA Champs','Hard','Elina Svitolina','Karolina Muchova',2.66,1.36,2.24,1.68,1966.2,1935.7,1.0,'Indian Wells WTA Champs, Hard, Elina Svitolina, Karolina Muchova, 2.66, 1.36, 2.24, 1.68, 1966.2, 1935.7, 66.0, 76.0, 1.0, 67.68, 68.95');
INSERT INTO "matches" VALUES('https://tennisinsight.com/match/260554206/2026-stockholm-atp-250/r16/lorenzo-sonego-vs-alejandro-tabilo','2026-11-13T11:55:50','Stockholm ATP 250','Indoor Hard','Lorenzo Sonego','Alejandro Tabilo',1.8,1.8,0.0,0.0,1665.0,1731.8,1.0,'Stockholm ATP 250, Indoor Hard, Lorenzo Sonego, Alejandro Tabilo, 1.8, 1.8, , , 1665.0, 1731.8, 48.0, 52.0, 1.0, 56.91, 32.0');
INSERT INTO "matches" VALUES('https://tennisinsight.com/match/260554201/2026-stockholm-atp-250/r16/taylor-fritz-vs-cameron-norrie','2026-11-13T11:55:50','Stockholm ATP 250','Indoor Hard','Taylor Fritz','Cameron Norrie',1.13,4.45,1.28,3.9,1899.6,1773.9,2.0,'Stockholm ATP 250, Indoor Hard, Taylor Fritz, Cameron Norrie, 1.13, 4.45, 1.28, 3.9, 1899.6, 1773.9, 68.0, 50.0, 2.0, 59.38, 53.33');
INSERT INTO "matches" VALUES('https://tennisinsight.com/match/260554204/2026-stockholm-atp-250/r16/borna-gojo-vs-ugo-humbert','2026-11-13T11:55:50','Stockholm ATP 250','Indoor Hard','Borna Gojo','Ugo Humbert',1.91,1.7,2.7,1.47,1612.8,1778.0,3.0,'Stockholm ATP 250, Indoor Hard, Borna Gojo, Ugo Humbert, 1.91, 1.7, 2.7, 1.47, 1612.8, 1778.0, 70.0, 50.0, 3.0, 62.75, 64.1');
INSERT INTO "matches" VALUES('https://tennisinsight.com/match/260554208/2026-stockholm-atp-250/r16/alexander-shevchenko-vs-casper-ruud','2026-11-13T11:55:50','Stockholm ATP 250','Indoor Hard','Alexander Shevchenko','Casper Ruud',5.55,1.07,4.75,1.19,1552.3,1894.5,1.0,'Stockholm ATP 250, Indoor Hard, Alexander Shevchenko, Casper Ruud, 5.55, 1.07, 4.75, 1.19, 1552.3, 1894.5, 48.0, 64.0, 1.0, 55.71, 61.46');
INSERT INTO "matches" VALUES('https://tennisinsight.com/match/260554202/2026-stockholm-atp-250/r16/miomir-kecmanovic-vs-holger-vitus-nodskov-rune','2026-11-13T11:55:50','Stockholm ATP 250','Indoor Hard','Miomir Kecmanovic','Holger Rune',1.78,1.82,3.18,1.35,1649.7,0.0,2.0,'Stockholm ATP 250, Indoor Hard, Miomir Kecmanovic, Holger Rune, 1.78, 1.82, 3.18, 1.35, 1649.7, , 46.0, 60.0, 2.0, 48.15, 69.0');
INSERT INTO "matches" VALUES('https://tennisinsight.com/match/260644201/2026-sopo-wta-ch/r16/tatjana-maria-vs-alice-tubello','2026-11-13T11:55:50','Sopo WTA Ch','Clay','Tatjana Maria','Alice Tubello',2.11,1.57,3.05,1.3,1614.8,1662.8,2.0,'Sopo WTA Ch, Clay, Tatjana Maria, Alice Tubello, 2.11, 1.57, 3.05, 1.3, 1614.8, 1662.8, 68.0, 68.0, 2.0, 53.24, 62.96');
INSERT INTO "matches" VALUES('https://tennisinsight.com/match/260644208/2026-sopo-wta-ch/r16/andrea-lazaro-garcia-vs-jazmin-ortenzi','2026-11-13T11:55:50','Sopo WTA Ch','Clay','Andrea Lazaro Garcia','Jazmin Ortenzi',1.31,2.88,1.11,5.37,1590.4,1480.9,3.0,'Sopo WTA Ch, Clay, Andrea Lazaro Garcia, Jazmin Ortenzi, 1.31, 2.88, 1.11, 5.37, 1590.4, 1480.9, 64.0, 58.0, 3.0, 55.42, 56.35');
INSERT INTO "matches" VALUES('https://tennisinsight.com/match/260644202/2026-sopo-wta-ch/r16/polona-hercog-vs-carole-monnet','2026-11-13T11:55:50','Sopo WTA Ch','Clay','Polona Hercog','Carole Monnet',1.28,3.01,2.2,1.65,1510.8,1546.3,2.0,'Sopo WTA Ch, Clay, Polona Hercog, Carole Monnet, 1.28, 3.01, 2.2, 1.65, 1510.8, 1546.3, 50.0, 42.0, 2.0, 66.02, 51.29');
INSERT INTO "matches" VALUES('https://tennisinsight.com/match/260644206/2026-sopo-wta-ch/r16/irene-burillo-escorihuela-vs-julia-grabher','2026-11-13T11:55:50','Sopo WTA Ch','Clay','Irene Burillo Escorihuela','Julia Grabher',5.34,1.08,3.35,1.29,1508.5,1640.6,1.0,'Sopo WTA Ch, Clay, Irene Burillo Escorihuela, Julia Grabher, 5.34, 1.08, 3.35, 1.29, 1508.5, 1640.6, 56.0, 60.0, 1.0, 53.2, 63.33');
INSERT INTO "matches" VALUES('https://tennisinsight.com/match/260644205/2026-sopo-wta-ch/r16/laura-samson-vs-sofia-costoulas','2026-11-13T11:55:50','Sopo WTA Ch','Clay','Laura Samson','Sofia Costoulas',1.11,4.8,1.34,3.05,1628.5,1421.0,3.0,'Sopo WTA Ch, Clay, Laura Samson, Sofia Costoulas, 1.11, 4.8, 1.34, 3.05, 1628.5, 1421.0, 64.0, 50.0, 3.0, 70.83, 48.08');
INSERT INTO "matches" VALUES('https://tennisinsight.com/match/260644207/2026-sopo-wta-ch/r16/lucia-bronzetti-vs-elizabeth-mandlik','2026-11-13T11:55:50','Sopo WTA Ch','Clay','Lucia Bronzetti','Elizabeth Mandlik',1.12,4.64,1.1,5.85,1573.8,1458.1,3.0,'Sopo WTA Ch, Clay, Lucia Bronzetti, Elizabeth Mandlik, 1.12, 4.64, 1.1, 5.85, 1573.8, 1458.1, 60.0, 54.0, 3.0, 54.8, 50.74');
INSERT INTO "matches" VALUES('https://tennisinsight.com/match/260644203/2026-sopo-wta-ch/r16/bianca-andreescu-vs-laura-pigossi','2026-11-13T11:55:50','Sopo WTA Ch','Clay','Bianca Andreescu','Laura Pigossi',1.09,5.26,1.05,8.5,1725.0,1460.5,3.0,'Sopo WTA Ch, Clay, Bianca Andreescu, Laura Pigossi, 1.09, 5.26, 1.05, 8.5, 1725.0, 1460.5, 64.0, 44.0, 3.0, 64.63, 50.24');
INSERT INTO "matches" VALUES('https://tennisinsight.com/match/260644204/2026-sopo-wta-ch/r16/maria-carle-vs-marina-bassols-ribera','2026-11-13T11:55:50','Sopo WTA Ch','Clay','Maria Carle','Marina Bassols Ribera',3.31,1.24,1.89,1.78,0.0,1574.9,1.0,'Sopo WTA Ch, Clay, Maria Carle, Marina Bassols Ribera, 3.31, 1.24, 1.89, 1.78, , 1574.9, 46.0, 60.0, 1.0, 59.55, 56.4');
INSERT INTO "matches" VALUES('https://tennisinsight.com/match/260564109/2026-indian-wells-wta-champs/rr/marta-kostyuk-vs-cori-gauff','2026-11-13T11:55:50','Indian Wells WTA Champs','Hard','Mirra Andreeva','Karolina Muchova',1.06,5.97,1.4,3.07,1982.0,1935.7,3.0,'Indian Wells WTA Champs, Hard, Mirra Andreeva, Karolina Muchova, 1.06, 5.97, 1.4, 3.07, 1982.0, 1935.7, 78.0, 74.0, 3.0, 73.08, 68.64, https://tennisinsight.com/match/260564111/2026-indian-wells-wta-champs/rr/mirra-andreeva-vs-karolina-muchovaIndian Wells WTA Champs, Hard, Marta Kostyuk, Coco Gauff, 5.31, 1.08, 3.5, 1.33, 1931.0, 2081.8, 72.0, 76.0, 2.0, 61.98, 72.2');
INSERT INTO "matches" VALUES('https://tennisinsight.com/match/260564110/2026-indian-wells-wta-champs/rr/jessica-pegula-vs-linda-noskova','2026-11-13T11:55:50','Indian Wells WTA Champs','Hard','Jessica Pegula','Linda Noskova',2.5,1.41,2.04,1.82,2057.6,1982.0,2.0,'Indian Wells WTA Champs, Hard, Jessica Pegula, Linda Noskova, 2.5, 1.41, 2.04, 1.82, 2057.6, 1982.0, 74.0, 76.0, 2.0, 67.89, 65.61');
INSERT INTO "matches" VALUES('https://tennisinsight.com/match/260554304/2026-stockholm-atp-250/qf/thiago-agustin-tirante-vs-alexander-shevchenko','2026-11-13T11:55:50','Stockholm ATP 250','Indoor Hard','Thiago Agustin Tirante','Alexander Shevchenko',1.77,1.83,1.93,1.81,1669.4,1552.3,2.0,'Stockholm ATP 250, Indoor Hard, Thiago Agustin Tirante, Alexander Shevchenko, 1.77, 1.83, 1.93, 1.81, 1669.4, 1552.3, 56.0, 48.0, 2.0, 42.11, 56.34');
INSERT INTO "matches" VALUES('https://tennisinsight.com/match/260554301/2026-stockholm-atp-250/qf/taylor-fritz-vs-holger-vitus-nodskov-rune','2026-11-13T11:55:50','Stockholm ATP 250','Indoor Hard','Taylor Fritz','Holger Rune',1.15,4.12,1.43,2.75,1899.6,0.0,3.0,'Stockholm ATP 250, Indoor Hard, Taylor Fritz, Holger Rune, 1.15, 4.12, 1.43, 2.75, 1899.6, , 68.0, 60.0, 3.0, 59.69, 69.31');
INSERT INTO "matches" VALUES('https://tennisinsight.com/match/260554302/2026-stockholm-atp-250/qf/lorenzo-musetti-vs-ugo-humbert','2026-11-13T11:55:50','Stockholm ATP 250','Indoor Hard','Lorenzo Musetti','Ugo Humbert',1.3,2.9,1.47,2.65,1850.5,1778.0,3.0,'Stockholm ATP 250, Indoor Hard, Lorenzo Musetti, Ugo Humbert, 1.3, 2.9, 1.47, 2.65, 1850.5, 1778.0, 66.0, 50.0, 3.0, 52.69, 64.33');
DELETE FROM "sqlite_sequence";
INSERT INTO "sqlite_sequence" VALUES('bets',1);
COMMIT;
