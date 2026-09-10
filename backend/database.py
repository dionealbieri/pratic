import sqlite3
import os
from datetime import datetime, date, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "banco", "pratic.db")

# Dados fixos para a migracao unica de padronizacao do catalogo de Chinelos
# (ver init_db). Gerados e validados manualmente a partir do levantamento fisico
# de estoque do usuario -- nao alterar sem revisar a migracao correspondente.
RENOMEACOES_CHINELO = {
    "CHI-001": "CHINELO BRANCO - 17/18 TRAD AZE",
    "CHI-002": "CHINELO BRANCO - 17/18 TRAD BR",
    "CHI-003": "CHINELO BRANCO - 17/18 TRAD PK",
    "CHI-004": "CHINELO BRANCO - 17/18 TRAD PT",
    "CHI-005": "CHINELO BRANCO - 17/18 TRAD VF",
    "CHI-006": "CHINELO BRANCO - 19/20 TRAD AZE",
    "CHI-007": "CHINELO BRANCO - 19/20 TRAD BR",
    "CHI-008": "CHINELO BRANCO - 19/20 TRAD PT",
    "CHI-009": "CHINELO BRANCO - 19/20 TRAD RS",
    "CHI-010": "CHINELO BRANCO - 19/20 TRAD AZF",
    "CHI-011": "CHINELO BRANCO - 21/22 TRAD BR",
    "CHI-012": "CHINELO BRANCO - 21/22 TRAD VF",
    "CHI-013": "CHINELO BRANCO - 21/22 TRAD PT",
    "CHI-014": "CHINELO BRANCO - 23/24 TRAD AMA1",
    "CHI-015": "CHINELO BRANCO - 23/24 TRAD AZE",
    "CHI-016": "CHINELO BRANCO - 23/24 TRAD BR",
    "CHI-017": "CHINELO BRANCO - 23/24 SLIM BR",
    "CHI-018": "CHINELO BRANCO - 23/24 SLIM BRD",
    "CHI-019": "CHINELO BRANCO - 23/24 SLIM CZ",
    "CHI-020": "CHINELO BRANCO - 21/22 TRAD RS",
    "CHI-021": "CHINELO BRANCO - 23/24 TRAD CR",
    "CHI-022": "CHINELO BRANCO - 23/24 SLIM DO",
    "CHI-023": "CHINELO BRANCO - 23/24 SLIM DOD",
    "CHI-024": "CHINELO BRANCO - 23/24 TRAD LJ",
    "CHI-025": "CHINELO BRANCO - 23/24 TRAD MR",
    "CHI-026": "CHINELO BRANCO - 23/24 SLIM PE",
    "CHI-027": "CHINELO BRANCO - 23/24 TRAD PK",
    "CHI-028": "CHINELO BRANCO - 23/24 SLIM PK",
    "CHI-029": "CHINELO BRANCO - 23/24 SLIM PKD",
    "CHI-030": "CHINELO BRANCO - 23/24 SLIM PKPD",
    "CHI-031": "CHINELO BRANCO - 23/24 TRAD PT",
    "CHI-032": "CHINELO BRANCO - 23/24 SLIM PT",
    "CHI-033": "CHINELO BRANCO - 23/24 SLIM RSP",
    "CHI-034": "CHINELO BRANCO - 23/24 TRAD VDC",
    "CHI-035": "CHINELO BRANCO - 23/24 SLIM VDP",
    "CHI-036": "CHINELO BRANCO - 23/24 TRAD VF",
    "CHI-037": "CHINELO BRANCO - 23/24 SLIM VP",
    "CHI-038": "CHINELO BRANCO - 25/26 TRAD AMA1",
    "CHI-039": "CHINELO BRANCO - 25/26 TRAD AZE",
    "CHI-040": "CHINELO BRANCO - 25/26 TRAD BR",
    "CHI-041": "CHINELO BRANCO - 25/26 SLIM BR",
    "CHI-042": "CHINELO BRANCO - 25/26 SLIM CZ",
    "CHI-043": "CHINELO BRANCO - 25/26 TRAD CR",
    "CHI-044": "CHINELO BRANCO - 25/26 TRAD DO",
    "CHI-045": "CHINELO BRANCO - 25/26 SLIM DO",
    "CHI-046": "CHINELO BRANCO - 25/26 SLIM DOD",
    "CHI-047": "CHINELO BRANCO - 25/26 TRAD LJ",
    "CHI-048": "CHINELO BRANCO - 25/26 TRAD MR",
    "CHI-049": "CHINELO BRANCO - 25/26 TRAD MRP",
    "CHI-050": "CHINELO BRANCO - 25/26 SLIM PE",
    "CHI-051": "CHINELO BRANCO - 25/26 TRAD PK",
    "CHI-052": "CHINELO BRANCO - 25/26 SLIM PK",
    "CHI-053": "CHINELO BRANCO - 25/26 SLIM PKD",
    "CHI-054": "CHINELO BRANCO - 25/26 TRAD PT",
    "CHI-055": "CHINELO BRANCO - 25/26 SLIM RSE",
    "CHI-056": "CHINELO BRANCO - 25/26 SLIM RSP",
    "CHI-057": "CHINELO BRANCO - 25/26 TRAD VDC",
    "CHI-058": "CHINELO BRANCO - 25/26 SLIM VDP",
    "CHI-059": "CHINELO BRANCO - 25/26 TRAD VF",
    "CHI-060": "CHINELO BRANCO - 25/26 SLIM VP",
    "CHI-061": "CHINELO BRANCO - 27/28 TRAD AMA1",
    "CHI-062": "CHINELO BRANCO - 27/28 TRAD AZE",
    "CHI-063": "CHINELO BRANCO - 27/28 TRAD BR",
    "CHI-064": "CHINELO BRANCO - 27/28 SLIM BR",
    "CHI-065": "CHINELO BRANCO - 27/28 SLIM BRAD",
    "CHI-066": "CHINELO BRANCO - 27/28 SLIM CZ",
    "CHI-067": "CHINELO BRANCO - 27/28 TRAD CR",
    "CHI-068": "CHINELO BRANCO - 27/28 SLIM DO",
    "CHI-069": "CHINELO BRANCO - 27/28 TRAD DO",
    "CHI-070": "CHINELO BRANCO - 27/28 SLIM DOD",
    "CHI-071": "CHINELO BRANCO - 27/28 TRAD LJ",
    "CHI-072": "CHINELO BRANCO - 27/28 TRAD MR",
    "CHI-073": "CHINELO BRANCO - 27/28 TRAD MRP",
    "CHI-074": "CHINELO BRANCO - 27/28 SLIM PE",
    "CHI-075": "CHINELO BRANCO - 27/28 TRAD PK",
    "CHI-076": "CHINELO BRANCO - 27/28 SLIM PK",
    "CHI-077": "CHINELO BRANCO - 27/28 SLIM PED",
    "CHI-078": "CHINELO BRANCO - 27/28 TRAD PT",
    "CHI-079": "CHINELO BRANCO - 27/28 SLIM PT",
    "CHI-080": "CHINELO BRANCO - 27/28 SLIM RSE",
    "CHI-081": "CHINELO BRANCO - 27/28 SLIM RSP",
    "CHI-082": "CHINELO BRANCO - 27/28 TRAD VD",
    "CHI-083": "CHINELO BRANCO - 27/28 SLIM VDP",
    "CHI-084": "CHINELO BRANCO - 27/28 TRAD VF",
    "CHI-085": "CHINELO BRANCO - 27/28 SLIM VP",
}

NOVOS_CHINELOS = [
    ("CHI-086", "CHINELO BRANCO - 29/30 TRAD BR", 21),
    ("CHI-087", "CHINELO BRANCO - 29/30 SLIM BR", 18),
    ("CHI-088", "CHINELO BRANCO - 29/30 SLIM BRD", 10),
    ("CHI-089", "CHINELO BRANCO - 29/30 SLIM CZ", 12),
    ("CHI-090", "CHINELO BRANCO - 29/30 TRAD CR", 6),
    ("CHI-091", "CHINELO BRANCO - 29/30 TRAD DO", 5),
    ("CHI-092", "CHINELO BRANCO - 29/30 SLIM DO", 12),
    ("CHI-093", "CHINELO BRANCO - 29/30 SLIM DOD", 5),
    ("CHI-094", "CHINELO BRANCO - 29/30 TRAD LJ", 5),
    ("CHI-095", "CHINELO BRANCO - 29/30 TRAD MR", 10),
    ("CHI-096", "CHINELO BRANCO - 29/30 TRAD MRP", 12),
    ("CHI-097", "CHINELO BRANCO - 29/30 SLIM PE", 16),
    ("CHI-098", "CHINELO BRANCO - 29/30 TRAD PK", 24),
    ("CHI-099", "CHINELO BRANCO - 29/30 SLIM PK", 11),
    ("CHI-100", "CHINELO BRANCO - 29/30 SLIM PKD", 2),
    ("CHI-101", "CHINELO BRANCO - 29/30 TRAD PT", 23),
    ("CHI-102", "CHINELO BRANCO - 29/30 SLIM PT", 17),
    ("CHI-103", "CHINELO BRANCO - 29/30 TRAD RSPE", 11),
    ("CHI-104", "CHINELO BRANCO - 29/30 SLIM ROPI", 12),
    ("CHI-105", "CHINELO BRANCO - 29/30 TRAD VD", 4),
    ("CHI-106", "CHINELO BRANCO - 29/30 SLIM VDP", 5),
    ("CHI-107", "CHINELO BRANCO - 29/30 TRAD VF", 5),
    ("CHI-108", "CHINELO BRANCO - 29/30 SLIM VP", 14),
    ("CHI-109", "CHINELO BRANCO - 31/32 TRAD AMA1", 3),
    ("CHI-110", "CHINELO BRANCO - 31/32 TRAD AZE", 14),
    ("CHI-111", "CHINELO BRANCO - 31/32 SLIM AZPE", 8),
    ("CHI-112", "CHINELO BRANCO - 31/32 TRAD BR", 27),
    ("CHI-113", "CHINELO BRANCO - 31/32 SLIM BR", 12),
    ("CHI-114", "CHINELO BRANCO - 31/32 SLIM CZ", 14),
    ("CHI-115", "CHINELO BRANCO - 31/32 TRAD CR", 5),
    ("CHI-116", "CHINELO BRANCO - 31/32 TRAD DO", 5),
    ("CHI-117", "CHINELO BRANCO - 31/32 SLIM DO", 5),
    ("CHI-118", "CHINELO BRANCO - 31/32 SLIM DOD", 5),
    ("CHI-119", "CHINELO BRANCO - 31/32 TRAD LJ", 5),
    ("CHI-120", "CHINELO BRANCO - 31/32 TRAD MR", 10),
    ("CHI-121", "CHINELO BRANCO - 31/32 TRAD MRP", 10),
    ("CHI-122", "CHINELO BRANCO - 31/32 SLIM PE", 16),
    ("CHI-123", "CHINELO BRANCO - 31/32 TRAD PK", 23),
    ("CHI-124", "CHINELO BRANCO - 31/32 SLIM PK", 11),
    ("CHI-125", "CHINELO BRANCO - 31/32 TRAD PT", 24),
    ("CHI-126", "CHINELO BRANCO - 31/32 SLIM PT", 42),
    ("CHI-127", "CHINELO BRANCO - 31/32 SLIM RSED", 13),
    ("CHI-128", "CHINELO BRANCO - 31/32 SLIM ROPD", 2),
    ("CHI-129", "CHINELO BRANCO - 31/32 SLIM ROPZ", 5),
    ("CHI-130", "CHINELO BRANCO - 31/32 TRAD VD", 3),
    ("CHI-131", "CHINELO BRANCO - 31/32 SLIM VDP", 1),
    ("CHI-132", "CHINELO BRANCO - 31/32 TRAD VF", 9),
    ("CHI-133", "CHINELO BRANCO - 31/32 SLIM VP", 24),
    ("CHI-134", "CHINELO BRANCO - 33/34 TRAD AMA1", 9),
    ("CHI-135", "CHINELO BRANCO - 33/34 SLIM AMA1", 4),
    ("CHI-136", "CHINELO BRANCO - 33/34 TRAD AZE", 20),
    ("CHI-137", "CHINELO BRANCO - 33/34 SLIM AZP", 10),
    ("CHI-138", "CHINELO BRANCO - 33/34 SLIM AZPE", 12),
    ("CHI-139", "CHINELO BRANCO - 33/34 TRAD BR", 18),
    ("CHI-140", "CHINELO BRANCO - 33/34 SLIM BR", 48),
    ("CHI-141", "CHINELO BRANCO - 33/34 SLIM CZ", 10),
    ("CHI-142", "CHINELO BRANCO - 33/34 SLIM DO", 27),
    ("CHI-143", "CHINELO BRANCO - 33/34 TRAD LJ", 5),
    ("CHI-144", "CHINELO BRANCO - 33/34 SLIM LJ", 5),
    ("CHI-145", "CHINELO BRANCO - 33/34 TRAD MR", 12),
    ("CHI-146", "CHINELO BRANCO - 33/34 SLIM MR", 4),
    ("CHI-147", "CHINELO BRANCO - 33/34 TRAD MRP", 12),
    ("CHI-148", "CHINELO BRANCO - 33/34 SLIM OV", 10),
    ("CHI-149", "CHINELO BRANCO - 33/34 SLIM PE", 14),
    ("CHI-150", "CHINELO BRANCO - 33/34 SLIM PK", 31),
    ("CHI-151", "CHINELO BRANCO - 33/34 TRAD PT", 31),
    ("CHI-152", "CHINELO BRANCO - 33/34 SLIM PT", 33),
    ("CHI-153", "CHINELO BRANCO - 33/34 SLIM RSB", 4),
    ("CHI-154", "CHINELO BRANCO - 33/34 SLIM RSBP", 10),
    ("CHI-155", "CHINELO BRANCO - 33/34 SLIM RSE", 2),
    ("CHI-156", "CHINELO BRANCO - 33/34 TRAD TR", 5),
    ("CHI-157", "CHINELO BRANCO - 33/34 SLIM TRG", 4),
    ("CHI-158", "CHINELO BRANCO - 33/34 TRAD VD", 2),
    ("CHI-159", "CHINELO BRANCO - 33/34 SLIM VDP", 23),
    ("CHI-160", "CHINELO BRANCO - 33/34 TRAD VF", 5),
    ("CHI-161", "CHINELO BRANCO - 33/34 SLIM VF", 7),
    ("CHI-162", "CHINELO BRANCO - 33/34 SLIM VP", 18),
    ("CHI-163", "CHINELO BRANCO - 33/34 SLIM VI", 8),
    ("CHI-164", "CHINELO BRANCO - 33/34 SLIM VIO", 10),
    ("CHI-165", "CHINELO BRANCO - 35/36 TRAD AMA1", 19),
    ("CHI-166", "CHINELO BRANCO - 35/36 SLIM AMA1", 1),
    ("CHI-167", "CHINELO BRANCO - 35/36 SLIM AZCP", 4),
    ("CHI-168", "CHINELO BRANCO - 35/36 TRAD AZE", 24),
    ("CHI-169", "CHINELO BRANCO - 35/36 SLIM AZEP", 40),
    ("CHI-170", "CHINELO BRANCO - 35/36 SLIM AZT", 29),
    ("CHI-171", "CHINELO BRANCO - 35/36 TRAD BR", 37),
    ("CHI-172", "CHINELO BRANCO - 35/36 SLIM BR", 51),
    ("CHI-173", "CHINELO BRANCO - 35/36 SLIM BRP", 14),
    ("CHI-174", "CHINELO BRANCO - 35/36 SLIM CZ", 103),
    ("CHI-175", "CHINELO BRANCO - 35/36 TRAD DO", 23),
    ("CHI-176", "CHINELO BRANCO - 35/36 SLIM DO", 72),
    ("CHI-177", "CHINELO BRANCO - 35/36 SLIM DOP", 10),
    ("CHI-178", "CHINELO BRANCO - 35/36 TRAD LJ", 5),
    ("CHI-179", "CHINELO BRANCO - 35/36 SLIM LJ", 11),
    ("CHI-180", "CHINELO BRANCO - 35/36 SLIM LIG", 12),
    ("CHI-181", "CHINELO BRANCO - 35/36 SLIM LAT", 9),
    ("CHI-182", "CHINELO BRANCO - 35/36 SLIM LLI", 9),
    ("CHI-183", "CHINELO BRANCO - 35/36 SLIM LRX", 7),
    ("CHI-184", "CHINELO BRANCO - 35/36 TRAD MR", 22),
    ("CHI-185", "CHINELO BRANCO - 35/36 SLIM MR", 1),
    ("CHI-186", "CHINELO BRANCO - 35/36 SLIM MS", 6),
    ("CHI-187", "CHINELO BRANCO - 35/36 SLIM MSL", 7),
    ("CHI-188", "CHINELO BRANCO - 35/36 SLIM PE", 16),
    ("CHI-189", "CHINELO BRANCO - 35/36 SLIM PEV", 21),
    ("CHI-190", "CHINELO BRANCO - 35/36 SLIM PK", 60),
    ("CHI-191", "CHINELO BRANCO - 35/36 SLIM PKPL", 5),
    ("CHI-192", "CHINELO BRANCO - 35/36 TRAD PT", 10),
    ("CHI-193", "CHINELO BRANCO - 35/36 SLIM PT", 59),
    ("CHI-194", "CHINELO BRANCO - 35/36 SLIM RS", 6),
    ("CHI-195", "CHINELO BRANCO - 35/36 SLIM RSB", 53),
    ("CHI-196", "CHINELO BRANCO - 35/36 SLIM RSBP", 9),
    ("CHI-197", "CHINELO BRANCO - 35/36 SLIM RSP", 51),
    ("CHI-198", "CHINELO BRANCO - 35/36 SLIM RO", 3),
    ("CHI-199", "CHINELO BRANCO - 35/36 SLIM TRG", 8),
    ("CHI-200", "CHINELO BRANCO - 35/36 TRAD VD", 13),
    ("CHI-201", "CHINELO BRANCO - 35/36 SLIM VDM", 22),
    ("CHI-202", "CHINELO BRANCO - 35/36 TRAD VF", 4),
    ("CHI-203", "CHINELO BRANCO - 35/36 SLIM VF", 22),
    ("CHI-204", "CHINELO BRANCO - 35/36 SLIM VP", 38),
    ("CHI-205", "CHINELO BRANCO - 35/36 SLIM VIO", 30),
    ("CHI-206", "CHINELO BRANCO - 37/38 TRAD AMA2", 28),
    ("CHI-207", "CHINELO BRANCO - 37/38 SLIM AZ", 4),
    ("CHI-208", "CHINELO BRANCO - 37/38 TRAD AZE", 28),
    ("CHI-209", "CHINELO BRANCO - 37/38 SLIM AZEP", 39),
    ("CHI-210", "CHINELO BRANCO - 37/38 SLIM AZP", 6),
    ("CHI-211", "CHINELO BRANCO - 37/38 TRAD AZR", 10),
    ("CHI-212", "CHINELO BRANCO - 37/38 SLIM AZT", 9),
    ("CHI-213", "CHINELO BRANCO - 37/38 SLIM AZTP", 50),
    ("CHI-214", "CHINELO BRANCO - 37/38 TRAD BR", 36),
    ("CHI-215", "CHINELO BRANCO - 37/38 SLIM BR", 28),
    ("CHI-216", "CHINELO BRANCO - 37/38 SLIM CZ", 168),
    ("CHI-217", "CHINELO BRANCO - 37/38 SLIM CR", 10),
    ("CHI-218", "CHINELO BRANCO - 37/38 TRAD DO", 12),
    ("CHI-219", "CHINELO BRANCO - 37/38 SLIM DO", 38),
    ("CHI-220", "CHINELO BRANCO - 37/38 SLIM LJ", 11),
    ("CHI-221", "CHINELO BRANCO - 37/38 SLIM LI", 19),
    ("CHI-222", "CHINELO BRANCO - 37/38 SLIM LIG", 52),
    ("CHI-223", "CHINELO BRANCO - 37/38 TRAD MR", 22),
    ("CHI-224", "CHINELO BRANCO - 37/38 SLIM OV", 12),
    ("CHI-225", "CHINELO BRANCO - 37/38 SLIM PE", 110),
    ("CHI-226", "CHINELO BRANCO - 37/38 SLIM PK", 98),
    ("CHI-227", "CHINELO BRANCO - 37/38 SLIM PKP", 13),
    ("CHI-228", "CHINELO BRANCO - 37/38 TRAD PT", 25),
    ("CHI-229", "CHINELO BRANCO - 37/38 SLIM PT", 46),
    ("CHI-230", "CHINELO BRANCO - 37/38 SLIM RSB", 91),
    ("CHI-231", "CHINELO BRANCO - 37/38 SLIM RSBP", 8),
    ("CHI-232", "CHINELO BRANCO - 37/38 SLIM RSE", 7),
    ("CHI-233", "CHINELO BRANCO - 37/38 SLIM ROP", 17),
    ("CHI-234", "CHINELO BRANCO - 37/38 SLIM RX", 17),
    ("CHI-235", "CHINELO BRANCO - 37/38 TRAD TR", 5),
    ("CHI-236", "CHINELO BRANCO - 37/38 SLIM TRG", 48),
    ("CHI-237", "CHINELO BRANCO - 37/38 TRAD VD", 24),
    ("CHI-238", "CHINELO BRANCO - 37/38 TRAD VDMP", 29),
    ("CHI-239", "CHINELO BRANCO - 37/38 TRAD VF", 5),
    ("CHI-240", "CHINELO BRANCO - 37/38 SLIM VF", 44),
    ("CHI-241", "CHINELO BRANCO - 37/38 SLIM VP", 196),
    ("CHI-242", "CHINELO BRANCO - 37/38 SLIM VIP", 20),
    ("CHI-243", "CHINELO BRANCO - 39/40 TRAD AMA1", 7),
    ("CHI-244", "CHINELO BRANCO - 39/40 TRAD AZC", 8),
    ("CHI-245", "CHINELO BRANCO - 39/40 SLIM AZCM", 3),
    ("CHI-246", "CHINELO BRANCO - 39/40 TRAD AZE", 9),
    ("CHI-247", "CHINELO BRANCO - 39/40 SLIM AZME", 15),
    ("CHI-248", "CHINELO BRANCO - 39/40 TRAD BR", 68),
    ("CHI-249", "CHINELO BRANCO - 39/40 SLIM BR", 74),
    ("CHI-250", "CHINELO BRANCO - 39/40 SLIM CZ", 93),
    ("CHI-251", "CHINELO BRANCO - 39/40 TRAD DO", 35),
    ("CHI-252", "CHINELO BRANCO - 39/40 SLIM DO", 10),
    ("CHI-253", "CHINELO BRANCO - 39/40 SLIM DOP", 15),
    ("CHI-254", "CHINELO BRANCO - 39/40 SLIM LJ", 7),
    ("CHI-255", "CHINELO BRANCO - 39/40 SLIM LIG", 32),
    ("CHI-256", "CHINELO BRANCO - 39/40 SLIM LAF", 3),
    ("CHI-257", "CHINELO BRANCO - 39/40 SLIM LAME", 10),
    ("CHI-258", "CHINELO BRANCO - 39/40 SLIM LLI", 19),
    ("CHI-259", "CHINELO BRANCO - 39/40 SLIM MG", 9),
    ("CHI-260", "CHINELO BRANCO - 39/40 SLIM MV", 5),
    ("CHI-261", "CHINELO BRANCO - 39/40 TRAD MR", 10),
    ("CHI-262", "CHINELO BRANCO - 39/40 SLIM MR", 4),
    ("CHI-263", "CHINELO BRANCO - 39/40 TRAD MRP", 13),
    ("CHI-264", "CHINELO BRANCO - 39/40 SLIM PEC", 8),
    ("CHI-265", "CHINELO BRANCO - 39/40 SLIM PEE", 14),
    ("CHI-266", "CHINELO BRANCO - 39/40 SLIM PEG", 23),
    ("CHI-267", "CHINELO BRANCO - 39/40 TRAD PT", 2),
    ("CHI-268", "CHINELO BRANCO - 39/40 SLIM PT", 37),
    ("CHI-269", "CHINELO BRANCO - 39/40 SLIM RSB", 56),
    ("CHI-270", "CHINELO BRANCO - 39/40 SLIM RSO", 47),
    ("CHI-271", "CHINELO BRANCO - 39/40 SLIM RSPC", 11),
    ("CHI-272", "CHINELO BRANCO - 39/40 SLIM RSPE", 37),
    ("CHI-273", "CHINELO BRANCO - 39/40 SLIM ROG", 8),
    ("CHI-274", "CHINELO BRANCO - 39/40 SLIM TF", 9),
    ("CHI-275", "CHINELO BRANCO - 39/40 SLIM TP", 32),
    ("CHI-276", "CHINELO BRANCO - 39/40 TRAD TR", 5),
    ("CHI-277", "CHINELO BRANCO - 39/40 SLIM TRG", 20),
    ("CHI-278", "CHINELO BRANCO - 39/40 TRAD VD1", 4),
    ("CHI-279", "CHINELO BRANCO - 39/40 TRAD VD2", 5),
    ("CHI-280", "CHINELO BRANCO - 39/40 SLIM VF", 21),
    ("CHI-281", "CHINELO BRANCO - 39/40 SLIM VP", 56),
    ("CHI-282", "CHINELO BRANCO - 39/40 SLIM VI", 21),
    ("CHI-283", "CHINELO BRANCO - 41/42 TRAD AMA2", 29),
    ("CHI-284", "CHINELO BRANCO - 41/42 TRAD AZ", 8),
    ("CHI-285", "CHINELO BRANCO - 41/42 TRAD AZE", 42),
    ("CHI-286", "CHINELO BRANCO - 41/42 TRAD AZR", 1),
    ("CHI-287", "CHINELO BRANCO - 41/42 TRAD CZ", 9),
    ("CHI-288", "CHINELO BRANCO - 41/42 TRAD BR", 47),
    ("CHI-289", "CHINELO BRANCO - 41/42 TRAD BRR", 1),
    ("CHI-290", "CHINELO BRANCO - 41/42 TRAD PK", 12),
    ("CHI-291", "CHINELO BRANCO - 41/42 TRAD PKP", 11),
    ("CHI-292", "CHINELO BRANCO - 41/42 TRAD PE", 2),
    ("CHI-293", "CHINELO BRANCO - 41/42 TRAD TR", 5),
    ("CHI-294", "CHINELO BRANCO - 41/42 TRAD DO", 14),
    ("CHI-295", "CHINELO BRANCO - 41/42 TRAD PT", 40),
    ("CHI-296", "CHINELO BRANCO - 41/42 TRAD VD", 51),
    ("CHI-297", "CHINELO BRANCO - 41/42 TRAD VDC", 5),
    ("CHI-298", "CHINELO BRANCO - 41/42 TRAD MR", 11),
    ("CHI-299", "CHINELO BRANCO - 43/44 TRAD AMA2", 10),
    ("CHI-300", "CHINELO BRANCO - 43/44 TRAD AZC", 6),
    ("CHI-301", "CHINELO BRANCO - 43/44 TRAD AZE", 38),
    ("CHI-302", "CHINELO BRANCO - 43/44 TRAD AZR", 1),
    ("CHI-303", "CHINELO BRANCO - 43/44 TRAD BR", 11),
    ("CHI-304", "CHINELO BRANCO - 43/44 TRAD DO", 16),
    ("CHI-305", "CHINELO BRANCO - 43/44 TRAD MR", 2),
    ("CHI-306", "CHINELO BRANCO - 43/44 TRAD PT", 4),
    ("CHI-307", "CHINELO BRANCO - 43/44 TRAD TR", 3),
    ("CHI-308", "CHINELO BRANCO - 43/44 TRAD VD", 12),
    ("CHI-309", "CHINELO BRANCO - 43/44 TRAD VDII", 3),
    ("CHI-310", "CHINELO BRANCO - 43/44 TRAD VF", 3),
    ("CHI-311", "CHINELO BRANCO - 45/46 TRAD BR", 16),
    ("CHI-312", "CHINELO BRANCO - 45/46 TRAD PT", 15),
]

MARCA_NOVOS_CHINELOS = {
    "CHI-086": "TRADICIONAL",
    "CHI-087": "SLIM",
    "CHI-088": "SLIM",
    "CHI-089": "SLIM",
    "CHI-090": "TRADICIONAL",
    "CHI-091": "TRADICIONAL",
    "CHI-092": "SLIM",
    "CHI-093": "SLIM",
    "CHI-094": "TRADICIONAL",
    "CHI-095": "TRADICIONAL",
    "CHI-096": "TRADICIONAL",
    "CHI-097": "SLIM",
    "CHI-098": "TRADICIONAL",
    "CHI-099": "SLIM",
    "CHI-100": "SLIM",
    "CHI-101": "TRADICIONAL",
    "CHI-102": "SLIM",
    "CHI-103": "TRADICIONAL",
    "CHI-104": "SLIM",
    "CHI-105": "TRADICIONAL",
    "CHI-106": "SLIM",
    "CHI-107": "TRADICIONAL",
    "CHI-108": "SLIM",
    "CHI-109": "TRADICIONAL",
    "CHI-110": "TRADICIONAL",
    "CHI-111": "SLIM",
    "CHI-112": "TRADICIONAL",
    "CHI-113": "SLIM",
    "CHI-114": "SLIM",
    "CHI-115": "TRADICIONAL",
    "CHI-116": "TRADICIONAL",
    "CHI-117": "SLIM",
    "CHI-118": "SLIM",
    "CHI-119": "TRADICIONAL",
    "CHI-120": "TRADICIONAL",
    "CHI-121": "TRADICIONAL",
    "CHI-122": "SLIM",
    "CHI-123": "TRADICIONAL",
    "CHI-124": "SLIM",
    "CHI-125": "TRADICIONAL",
    "CHI-126": "SLIM",
    "CHI-127": "SLIM",
    "CHI-128": "SLIM",
    "CHI-129": "SLIM",
    "CHI-130": "TRADICIONAL",
    "CHI-131": "SLIM",
    "CHI-132": "TRADICIONAL",
    "CHI-133": "SLIM",
    "CHI-134": "TRADICIONAL",
    "CHI-135": "SLIM",
    "CHI-136": "TRADICIONAL",
    "CHI-137": "SLIM",
    "CHI-138": "SLIM",
    "CHI-139": "TRADICIONAL",
    "CHI-140": "SLIM",
    "CHI-141": "SLIM",
    "CHI-142": "SLIM",
    "CHI-143": "TRADICIONAL",
    "CHI-144": "SLIM",
    "CHI-145": "TRADICIONAL",
    "CHI-146": "SLIM",
    "CHI-147": "TRADICIONAL",
    "CHI-148": "SLIM",
    "CHI-149": "SLIM",
    "CHI-150": "SLIM",
    "CHI-151": "TRADICIONAL",
    "CHI-152": "SLIM",
    "CHI-153": "SLIM",
    "CHI-154": "SLIM",
    "CHI-155": "SLIM",
    "CHI-156": "TRADICIONAL",
    "CHI-157": "SLIM",
    "CHI-158": "TRADICIONAL",
    "CHI-159": "SLIM",
    "CHI-160": "TRADICIONAL",
    "CHI-161": "SLIM",
    "CHI-162": "SLIM",
    "CHI-163": "SLIM",
    "CHI-164": "SLIM",
    "CHI-165": "TRADICIONAL",
    "CHI-166": "SLIM",
    "CHI-167": "SLIM",
    "CHI-168": "TRADICIONAL",
    "CHI-169": "SLIM",
    "CHI-170": "SLIM",
    "CHI-171": "TRADICIONAL",
    "CHI-172": "SLIM",
    "CHI-173": "SLIM",
    "CHI-174": "SLIM",
    "CHI-175": "TRADICIONAL",
    "CHI-176": "SLIM",
    "CHI-177": "SLIM",
    "CHI-178": "TRADICIONAL",
    "CHI-179": "SLIM",
    "CHI-180": "SLIM",
    "CHI-181": "SLIM",
    "CHI-182": "SLIM",
    "CHI-183": "SLIM",
    "CHI-184": "TRADICIONAL",
    "CHI-185": "SLIM",
    "CHI-186": "SLIM",
    "CHI-187": "SLIM",
    "CHI-188": "SLIM",
    "CHI-189": "SLIM",
    "CHI-190": "SLIM",
    "CHI-191": "SLIM",
    "CHI-192": "TRADICIONAL",
    "CHI-193": "SLIM",
    "CHI-194": "SLIM",
    "CHI-195": "SLIM",
    "CHI-196": "SLIM",
    "CHI-197": "SLIM",
    "CHI-198": "SLIM",
    "CHI-199": "SLIM",
    "CHI-200": "TRADICIONAL",
    "CHI-201": "SLIM",
    "CHI-202": "TRADICIONAL",
    "CHI-203": "SLIM",
    "CHI-204": "SLIM",
    "CHI-205": "SLIM",
    "CHI-206": "TRADICIONAL",
    "CHI-207": "SLIM",
    "CHI-208": "TRADICIONAL",
    "CHI-209": "SLIM",
    "CHI-210": "SLIM",
    "CHI-211": "TRADICIONAL",
    "CHI-212": "SLIM",
    "CHI-213": "SLIM",
    "CHI-214": "TRADICIONAL",
    "CHI-215": "SLIM",
    "CHI-216": "SLIM",
    "CHI-217": "SLIM",
    "CHI-218": "TRADICIONAL",
    "CHI-219": "SLIM",
    "CHI-220": "SLIM",
    "CHI-221": "SLIM",
    "CHI-222": "SLIM",
    "CHI-223": "TRADICIONAL",
    "CHI-224": "SLIM",
    "CHI-225": "SLIM",
    "CHI-226": "SLIM",
    "CHI-227": "SLIM",
    "CHI-228": "TRADICIONAL",
    "CHI-229": "SLIM",
    "CHI-230": "SLIM",
    "CHI-231": "SLIM",
    "CHI-232": "SLIM",
    "CHI-233": "SLIM",
    "CHI-234": "SLIM",
    "CHI-235": "TRADICIONAL",
    "CHI-236": "SLIM",
    "CHI-237": "TRADICIONAL",
    "CHI-238": "TRADICIONAL",
    "CHI-239": "TRADICIONAL",
    "CHI-240": "SLIM",
    "CHI-241": "SLIM",
    "CHI-242": "SLIM",
    "CHI-243": "TRADICIONAL",
    "CHI-244": "TRADICIONAL",
    "CHI-245": "SLIM",
    "CHI-246": "TRADICIONAL",
    "CHI-247": "SLIM",
    "CHI-248": "TRADICIONAL",
    "CHI-249": "SLIM",
    "CHI-250": "SLIM",
    "CHI-251": "TRADICIONAL",
    "CHI-252": "SLIM",
    "CHI-253": "SLIM",
    "CHI-254": "SLIM",
    "CHI-255": "SLIM",
    "CHI-256": "SLIM",
    "CHI-257": "SLIM",
    "CHI-258": "SLIM",
    "CHI-259": "SLIM",
    "CHI-260": "SLIM",
    "CHI-261": "TRADICIONAL",
    "CHI-262": "SLIM",
    "CHI-263": "TRADICIONAL",
    "CHI-264": "SLIM",
    "CHI-265": "SLIM",
    "CHI-266": "SLIM",
    "CHI-267": "TRADICIONAL",
    "CHI-268": "SLIM",
    "CHI-269": "SLIM",
    "CHI-270": "SLIM",
    "CHI-271": "SLIM",
    "CHI-272": "SLIM",
    "CHI-273": "SLIM",
    "CHI-274": "SLIM",
    "CHI-275": "SLIM",
    "CHI-276": "TRADICIONAL",
    "CHI-277": "SLIM",
    "CHI-278": "TRADICIONAL",
    "CHI-279": "TRADICIONAL",
    "CHI-280": "SLIM",
    "CHI-281": "SLIM",
    "CHI-282": "SLIM",
    "CHI-283": "TRADICIONAL",
    "CHI-284": "TRADICIONAL",
    "CHI-285": "TRADICIONAL",
    "CHI-286": "TRADICIONAL",
    "CHI-287": "TRADICIONAL",
    "CHI-288": "TRADICIONAL",
    "CHI-289": "TRADICIONAL",
    "CHI-290": "TRADICIONAL",
    "CHI-291": "TRADICIONAL",
    "CHI-292": "TRADICIONAL",
    "CHI-293": "TRADICIONAL",
    "CHI-294": "TRADICIONAL",
    "CHI-295": "TRADICIONAL",
    "CHI-296": "TRADICIONAL",
    "CHI-297": "TRADICIONAL",
    "CHI-298": "TRADICIONAL",
    "CHI-299": "TRADICIONAL",
    "CHI-300": "TRADICIONAL",
    "CHI-301": "TRADICIONAL",
    "CHI-302": "TRADICIONAL",
    "CHI-303": "TRADICIONAL",
    "CHI-304": "TRADICIONAL",
    "CHI-305": "TRADICIONAL",
    "CHI-306": "TRADICIONAL",
    "CHI-307": "TRADICIONAL",
    "CHI-308": "TRADICIONAL",
    "CHI-309": "TRADICIONAL",
    "CHI-310": "TRADICIONAL",
    "CHI-311": "TRADICIONAL",
    "CHI-312": "TRADICIONAL",
}


def _pascoa(ano: int) -> date:
    """Calcula a data da Páscoa (algoritmo de Gauss/computus gregoriano)."""
    a = ano % 19
    b = ano // 100
    c = ano % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return date(ano, mes, dia)

def _feriados_nacionais(ano: int):
    """Feriados nacionais fixos + móveis (calculados a partir da Páscoa) de um
    ano qualquer. Feriados estaduais/municipais não entram aqui — são
    cadastrados manualmente pelo usuário."""
    pascoa = _pascoa(ano)
    return [
        (f"{ano}-01-01", "Confraternização Universal"),
        ((pascoa - timedelta(days=48)).isoformat(), "Carnaval (segunda-feira)"),
        ((pascoa - timedelta(days=47)).isoformat(), "Carnaval (terça-feira)"),
        ((pascoa - timedelta(days=2)).isoformat(), "Sexta-feira Santa"),
        (f"{ano}-04-21", "Tiradentes"),
        (f"{ano}-05-01", "Dia do Trabalho"),
        ((pascoa + timedelta(days=60)).isoformat(), "Corpus Christi"),
        (f"{ano}-09-07", "Independência do Brasil"),
        (f"{ano}-10-12", "Nossa Senhora Aparecida"),
        (f"{ano}-11-02", "Finados"),
        (f"{ano}-11-15", "Proclamação da República"),
        (f"{ano}-11-20", "Dia Nacional de Zumbi e da Consciência Negra"),
        (f"{ano}-12-25", "Natal"),
    ]

def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_conn()
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS maquinas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            setor TEXT,
            meta_padrao REAL DEFAULT 8000,
            ativa INTEGER DEFAULT 1,
            criado_em TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS comunicacao_recados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            texto TEXT NOT NULL,
            autor_id INTEGER,
            autor_nome TEXT,
            autor_setor TEXT,
            criado_em TEXT DEFAULT (datetime('now')),
            resolvido INTEGER DEFAULT 0,
            resolvido_por TEXT,
            resolvido_em TEXT
        );

        CREATE TABLE IF NOT EXISTS colaborador_tipos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE NOT NULL,
            ativo INTEGER DEFAULT 1,
            criado_em TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS colaboradores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            tipo TEXT NOT NULL,
            maquina_id INTEGER,
            ativo INTEGER DEFAULT 1,
            criado_em TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (maquina_id) REFERENCES maquinas(id)
        );

        CREATE TABLE IF NOT EXISTS producao_diaria (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            colaborador_id INTEGER NOT NULL,
            maquina_id INTEGER NOT NULL,
            data TEXT NOT NULL,
            mes_referencia TEXT NOT NULL,
            meta REAL NOT NULL,
            producao REAL NOT NULL,
            excedente REAL,
            produto_estoque_id INTEGER DEFAULT NULL,
            perda_quantidade REAL DEFAULT 0,
            sobra_quantidade REAL DEFAULT 0,
            pedido_numero TEXT,
            criado_em TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (colaborador_id) REFERENCES colaboradores(id),
            FOREIGN KEY (maquina_id) REFERENCES maquinas(id)
        );

        -- Etapa de pintura, anterior a impressao (producao_diaria). Registro de
        -- produtividade/perdas/sobras apenas — NAO mexe em estoque_saldo nem
        -- em meta/premiacao, por definicao (a baixa de estoque continua
        -- acontecendo so na impressao, como ja era).
        CREATE TABLE IF NOT EXISTS producao_pintura (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            colaborador_id INTEGER NOT NULL,
            data TEXT NOT NULL,
            mes_referencia TEXT NOT NULL,
            pedido_numero TEXT,
            produto_estoque_id INTEGER DEFAULT NULL,
            quantidade_cores INTEGER NOT NULL DEFAULT 1,
            quantidade_pintada REAL NOT NULL DEFAULT 0,
            perda_quantidade REAL DEFAULT 0,
            perda_tipo TEXT,
            perda_observacao TEXT,
            sobra_quantidade REAL DEFAULT 0,
            criado_em TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (colaborador_id) REFERENCES colaboradores(id),
            FOREIGN KEY (produto_estoque_id) REFERENCES estoque_produtos(id)
        );

        CREATE TABLE IF NOT EXISTS premiacao_operador (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            colaborador_id INTEGER NOT NULL,
            mes_referencia TEXT NOT NULL,
            total_producao REAL,
            dias_trabalhados INTEGER,
            media_diaria REAL,
            meta REAL,
            excedente_total REAL,
            elegivel INTEGER DEFAULT 0,
            valor_premio REAL DEFAULT 0,
            ranking INTEGER,
            fechado INTEGER DEFAULT 0,
            criado_em TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (colaborador_id) REFERENCES colaboradores(id)
        );

        CREATE TABLE IF NOT EXISTS premiacao_auxiliar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            colaborador_id INTEGER NOT NULL,
            mes_referencia TEXT NOT NULL,
            posicao INTEGER,
            valor_bonus REAL DEFAULT 0,
            observacao TEXT,
            criado_em TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (colaborador_id) REFERENCES colaboradores(id)
        );



        CREATE TABLE IF NOT EXISTS epis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            categoria TEXT,
            descricao TEXT,
            ativo INTEGER DEFAULT 1,
            criado_em TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS funcao_epis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            funcao TEXT NOT NULL,
            epi_id INTEGER NOT NULL,
            FOREIGN KEY (epi_id) REFERENCES epis(id)
        );

        CREATE TABLE IF NOT EXISTS epi_entregas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            colaborador_id INTEGER NOT NULL,
            epi_id INTEGER NOT NULL,
            data_entrega TEXT NOT NULL,
            data_validade TEXT NOT NULL,
            motivo TEXT,
            responsavel TEXT,
            observacao TEXT,
            status TEXT DEFAULT 'ativo',
            criado_em TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (colaborador_id) REFERENCES colaboradores(id),
            FOREIGN KEY (epi_id) REFERENCES epis(id)
        );

        CREATE TABLE IF NOT EXISTS estoque_categorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            descricao TEXT,
            tipo TEXT DEFAULT 'producao',
            criado_em TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS estoque_produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT,
            categoria_id INTEGER,
            nome TEXT NOT NULL,
            marca TEXT,
            unidade TEXT DEFAULT 'unidade',
            estoque_minimo REAL DEFAULT 0,
            ativo INTEGER DEFAULT 1,
            criado_em TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (categoria_id) REFERENCES estoque_categorias(id)
        );

        CREATE TABLE IF NOT EXISTS estoque_saldo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            produto_id INTEGER UNIQUE,
            quantidade REAL DEFAULT 0,
            ultima_atualizacao TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (produto_id) REFERENCES estoque_produtos(id)
        );

        CREATE TABLE IF NOT EXISTS estoque_movimentacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            produto_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            quantidade REAL NOT NULL,
            saldo_anterior REAL,
            saldo_posterior REAL,
            motivo TEXT,
            tipo_perda TEXT,
            responsavel TEXT,
            fornecedor TEXT,
            custo_unitario REAL,
            observacao TEXT,
            data TEXT NOT NULL,
            nota_fiscal TEXT,
            criado_em TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (produto_id) REFERENCES estoque_produtos(id)
        );
        -- producao_diaria_id: adicionada via migracao abaixo (precisa existir a
        -- tabela producao_diaria primeiro, entao o ALTER TABLE fica fora do
        -- bloco executescript, junto das outras migracoes idempotentes)

        CREATE TABLE IF NOT EXISTS configuracoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chave TEXT UNIQUE NOT NULL,
            valor TEXT NOT NULL,
            descricao TEXT
        );

        CREATE TABLE IF NOT EXISTS pedidos_clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cnpj TEXT,
            razao_social TEXT NOT NULL,
            nome_fantasia TEXT,
            ie TEXT,
            email TEXT,
            telefone TEXT,
            cep TEXT,
            logradouro TEXT,
            numero TEXT,
            complemento TEXT,
            bairro TEXT,
            cidade TEXT,
            uf TEXT,
            observacoes TEXT,
            ativo INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS pedidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_pedido TEXT NOT NULL,
            cliente_id INTEGER NOT NULL,
            prazo_entrega TEXT NOT NULL,
            vendedor TEXT,
            observacoes TEXT,
            status TEXT DEFAULT 'aberto',
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (cliente_id) REFERENCES pedidos_clientes(id)
        );

        CREATE TABLE IF NOT EXISTS pedidos_itens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pedido_id INTEGER NOT NULL,
            produto_id INTEGER,
            descricao TEXT NOT NULL,
            quantidade REAL NOT NULL,
            unidade TEXT DEFAULT 'unidade',
            qtd_produzida REAL DEFAULT 0,
            status TEXT DEFAULT 'aberto',
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (pedido_id) REFERENCES pedidos(id)
        );

        CREATE TABLE IF NOT EXISTS auditoria (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT DEFAULT 'sistema',
            acao TEXT NOT NULL,
            entidade TEXT NOT NULL,
            entidade_id INTEGER,
            descricao TEXT,
            valor_anterior TEXT,
            valor_novo TEXT,
            criado_em TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS app_backups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            arquivo TEXT NOT NULL,
            caminho TEXT NOT NULL,
            tamanho_bytes INTEGER DEFAULT 0,
            motivo TEXT,
            criado_em TEXT DEFAULT (datetime('now','localtime'))
        );
    """)

    # Tabelas de segurança para controle de acesso e sessões
    c.executescript("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('gestor', 'producao', 'comercial', 'estoque')),
            nome TEXT NOT NULL,
            ativo INTEGER DEFAULT 1,
            deve_alterar_senha INTEGER DEFAULT 1,
            criado_em TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS sessoes (
            session_id TEXT PRIMARY KEY,
            usuario_id INTEGER NOT NULL,
            expira_em TEXT NOT NULL,
            criado_em TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
        );
    """)

    # Adicionar coluna deve_alterar_senha se não existir para bancos de dados já criados
    try:
        c.execute("ALTER TABLE usuarios ADD COLUMN deve_alterar_senha INTEGER DEFAULT 1")
        # Como o banco de dados já existia, definimos deve_alterar_senha = 0 para todos os usuários atuais
        # para que o acesso deles não seja interrompido abruptamente. Novos usuários criados herdarão 1.
        c.execute("UPDATE usuarios SET deve_alterar_senha = 0")
    except sqlite3.OperationalError:
        pass

    # Liberação da Comunicação por usuário (0 = não participa, 1 = participa)
    try:
        c.execute("ALTER TABLE usuarios ADD COLUMN comunicacao_ativa INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    # Liberação de canais por usuário (lista separada por vírgulas, ex: 'geral,producao')
    try:
        c.execute("ALTER TABLE usuarios ADD COLUMN canais_permitidos TEXT DEFAULT 'geral'")
        # Para usuários antigos (não gestores), liberamos também o canal do próprio setor (role)
        c.execute("""
            UPDATE usuarios 
            SET canais_permitidos = 'geral,' || role 
            WHERE role != 'gestor' AND role IS NOT NULL
        """)
        # Para gestores, liberamos todos os canais por padrão
        c.execute("""
            UPDATE usuarios 
            SET canais_permitidos = 'geral,producao,comercial,estoque' 
            WHERE role = 'gestor'
        """)
    except sqlite3.OperationalError:
        pass

    # Seed de usuários padrão se a tabela de usuários estiver vazia
    c.execute("SELECT COUNT(*) FROM usuarios")
    if c.fetchone()[0] == 0:
        import hashlib
        import secrets
        
        def _hash_pass(password: str) -> str:
            salt = secrets.token_bytes(16)
            key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
            return salt.hex() + "." + key.hex()
            
        default_users = [
            ("admin", _hash_pass("admin"), "gestor", "Administrador", 0),
            ("producao", _hash_pass("producao123"), "producao", "Produção", 0),
            ("comercial", _hash_pass("comercial123"), "comercial", "Comercial", 0),
            ("estoque", _hash_pass("estoque123"), "estoque", "Almoxarifado", 0)
        ]
        c.executemany("""
            INSERT INTO usuarios (username, password_hash, role, nome, deve_alterar_senha)
            VALUES (?, ?, ?, ?, ?)
        """, default_users)


    # Migrações leves para bancos já existentes
    # Tipos de colaboradores configuráveis: remove a trava antiga que aceitava somente operador/auxiliar
    # e cria uma tabela simples para o usuário cadastrar novas funções/tipos pela tela.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS colaborador_tipos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE NOT NULL,
            ativo INTEGER DEFAULT 1,
            criado_em TEXT DEFAULT (datetime('now'))
        )
    """)
    for tipo_padrao in ("operador", "auxiliar"):
        conn.execute("INSERT OR IGNORE INTO colaborador_tipos (nome, ativo) VALUES (?, 1)", (tipo_padrao,))
    for row in conn.execute("SELECT DISTINCT tipo FROM colaboradores WHERE COALESCE(tipo,'')<>''").fetchall():
        conn.execute("INSERT OR IGNORE INTO colaborador_tipos (nome, ativo) VALUES (?, 1)", (row[0],))

    # Unidades de medida configuráveis: cadastradas pela tela de Produtos (opção
    # "+ Nova unidade") e reaproveitadas em Pedidos e Movimentações.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS estoque_unidades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE NOT NULL,
            criado_em TEXT DEFAULT (datetime('now'))
        )
    """)
    for unidade_padrao in ("unidade", "und", "milheiro", "kg", "litro", "metro", "caixa", "pacote", "par"):
        conn.execute("INSERT OR IGNORE INTO estoque_unidades (nome) VALUES (?)", (unidade_padrao,))
    for row in conn.execute("SELECT DISTINCT unidade FROM estoque_produtos WHERE COALESCE(unidade,'')<>''").fetchall():
        conn.execute("INSERT OR IGNORE INTO estoque_unidades (nome) VALUES (?)", (row[0],))

    # Migração única: padronização do catálogo de Chinelos.
    #   1) Renomeia os 85 produtos existentes de "TIRAS ..." para o padrão
    #      "CHINELO BRANCO - <numeração> <TIPO> <CÓDIGO COR>" e ajusta a unidade para "par".
    #   2) Cria os 227 novos SKUs (numerações 29/30 a 45/46) e lança a entrada de
    #      estoque inicial de cada um, conforme levantamento físico do usuário.
    # Idempotente: cada produto novo só é criado se o código ainda não existir.
    _chi_cat = conn.execute("SELECT id FROM estoque_categorias WHERE UPPER(nome)='CHINELOS'").fetchone()
    if _chi_cat:
        _chi_cat_id = _chi_cat["id"]

        for _codigo, _nome_novo in RENOMEACOES_CHINELO.items():
            conn.execute(
                "UPDATE estoque_produtos SET nome=?, unidade='par' WHERE codigo=? AND categoria_id=?",
                (_nome_novo, _codigo, _chi_cat_id)
            )

        for _codigo, _nome, _qtd in NOVOS_CHINELOS:
            if conn.execute("SELECT id FROM estoque_produtos WHERE codigo=?", (_codigo,)).fetchone():
                continue
            _cur = conn.cursor()
            _cur.execute(
                "INSERT INTO estoque_produtos (codigo, categoria_id, nome, marca, unidade, estoque_minimo, ativo) "
                "VALUES (?, ?, ?, ?, 'par', 0, 1)",
                (_codigo, _chi_cat_id, _nome, MARCA_NOVOS_CHINELOS.get(_codigo))
            )
            _produto_id = _cur.lastrowid
            if _qtd > 0:
                _cur.execute(
                    "INSERT INTO estoque_movimentacoes "
                    "(produto_id, tipo, quantidade, saldo_anterior, saldo_posterior, motivo, data) "
                    "VALUES (?, 'entrada', ?, 0, ?, 'Saldo inicial - padronização do catálogo de chinelos', date('now'))",
                    (_produto_id, _qtd, _qtd)
                )
                conn.execute("INSERT OR IGNORE INTO estoque_saldo (produto_id, quantidade) VALUES (?, ?)", (_produto_id, _qtd))

        # Correção: os 227 produtos acima já podem ter sido criados por uma versão
        # anterior desta migração que esqueceu de gravar a marca (Tradicional/Slim).
        # Preenche a marca em qualquer um deles que ainda esteja em branco.
        for _codigo, _marca in MARCA_NOVOS_CHINELOS.items():
            conn.execute(
                "UPDATE estoque_produtos SET marca=? WHERE codigo=? AND categoria_id=? AND COALESCE(marca,'')=''",
                (_marca, _codigo, _chi_cat_id)
            )

    # Migração: controle por tipo de colaborador
    #   aparece_producao = aparece na seleção da Produção Diária e conta nos totais/ranking
    #   concorre_premio  = concorre ao prêmio de operador
    cols_tipos = [r[1] for r in conn.execute("PRAGMA table_info(colaborador_tipos)").fetchall()]
    primeira_migracao_flags = "aparece_producao" not in cols_tipos
    if "aparece_producao" not in cols_tipos:
        conn.execute("ALTER TABLE colaborador_tipos ADD COLUMN aparece_producao INTEGER DEFAULT 0")
    if "concorre_premio" not in cols_tipos:
        conn.execute("ALTER TABLE colaborador_tipos ADD COLUMN concorre_premio INTEGER DEFAULT 1")
    if primeira_migracao_flags:
        # Defaults aplicados só na primeira migração (não sobrescreve escolhas futuras do gestor)
        conn.execute("UPDATE colaborador_tipos SET aparece_producao=1, concorre_premio=1 WHERE LOWER(nome)='operador'")
        conn.execute("UPDATE colaborador_tipos SET aparece_producao=0 WHERE LOWER(nome)='auxiliar'")
        # Tipos de liderança (lider, líder, operador lider, operador líder, etc.):
        # produzem como operador, mas não concorrem ao prêmio.
        conn.execute("""
            UPDATE colaborador_tipos
               SET aparece_producao=1, concorre_premio=0
             WHERE nome LIKE '%lider%' OR nome LIKE '%líder%'
        """)

    # Migração: módulo de vendas (preço no produto, valores no item, totais e parcelas do pedido)
    cols_prod = [r[1] for r in conn.execute("PRAGMA table_info(estoque_produtos)").fetchall()]
    if "preco" not in cols_prod:
        conn.execute("ALTER TABLE estoque_produtos ADD COLUMN preco REAL DEFAULT 0")
    if "custo" not in cols_prod:
        conn.execute("ALTER TABLE estoque_produtos ADD COLUMN custo REAL DEFAULT 0")
    if "oculta_pdv" not in cols_prod:
        conn.execute("ALTER TABLE estoque_produtos ADD COLUMN oculta_pdv INTEGER DEFAULT 0")
    # Migração: dados da embalagem (dimensões e peso) no produto
    if "embalagem_comprimento" not in cols_prod:
        conn.execute("ALTER TABLE estoque_produtos ADD COLUMN embalagem_comprimento REAL DEFAULT 0")
    if "embalagem_largura" not in cols_prod:
        conn.execute("ALTER TABLE estoque_produtos ADD COLUMN embalagem_largura REAL DEFAULT 0")
    if "embalagem_altura" not in cols_prod:
        conn.execute("ALTER TABLE estoque_produtos ADD COLUMN embalagem_altura REAL DEFAULT 0")
    if "embalagem_peso" not in cols_prod:
        conn.execute("ALTER TABLE estoque_produtos ADD COLUMN embalagem_peso REAL DEFAULT 0")
    cols_cat = [r[1] for r in conn.execute("PRAGMA table_info(estoque_categorias)").fetchall()]
    if "parent_id" not in cols_cat:
        conn.execute("ALTER TABLE estoque_categorias ADD COLUMN parent_id INTEGER")
    if "oculta_pdv" not in cols_cat:
        conn.execute("ALTER TABLE estoque_categorias ADD COLUMN oculta_pdv INTEGER DEFAULT 0")
    cols_pi = [r[1] for r in conn.execute("PRAGMA table_info(pedidos_itens)").fetchall()]
    if "valor_unitario" not in cols_pi:
        conn.execute("ALTER TABLE pedidos_itens ADD COLUMN valor_unitario REAL DEFAULT 0")
    if "desconto" not in cols_pi:
        conn.execute("ALTER TABLE pedidos_itens ADD COLUMN desconto REAL DEFAULT 0")
    if "status_separacao" not in cols_pi:
        conn.execute("ALTER TABLE pedidos_itens ADD COLUMN status_separacao TEXT")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS producao_programada (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pedido_item_id INTEGER NOT NULL,
            data_programada TEXT NOT NULL,
            quantidade_programada REAL NOT NULL,
            criado_em TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (pedido_item_id) REFERENCES pedidos_itens(id)
        )
    """)
    # Vincula cada movimentacao de estoque ao lancamento de producao que a
    # gerou, com precisao (id exato) em vez de tentar re-identificar por
    # operador+data+produto+texto do motivo — essa combinacao "fuzzy" e
    # ambigua quando o mesmo operador tem mais de um lancamento do mesmo
    # produto no mesmo dia (comum na pratica), fazendo editar/excluir UM
    # lancamento reverter/apagar por engano a movimentacao de OUTRO.
    cols_mov = [r[1] for r in conn.execute("PRAGMA table_info(estoque_movimentacoes)").fetchall()]
    if "producao_diaria_id" not in cols_mov:
        conn.execute("ALTER TABLE estoque_movimentacoes ADD COLUMN producao_diaria_id INTEGER")
    if "pedido_numero" not in cols_mov:
        # coluna própria pro número do pedido — antes só existia escondido
        # dentro do texto do motivo ("Separação pedido X"), sem dar pra
        # filtrar/consultar as saídas de um pedido específico
        conn.execute("ALTER TABLE estoque_movimentacoes ADD COLUMN pedido_numero TEXT")

    # Preenchimento retroativo (idempotente, roda sem custo depois da primeira
    # vez): movimentações antigas ligadas a um lançamento de produção
    # (producao_diaria_id) já tinham o número do pedido gravado ali — só não
    # existia essa coluna própria ainda. Recupera de lá, sem precisar mexer
    # em nenhum lançamento manualmente.
    conn.execute("""
        UPDATE estoque_movimentacoes
        SET pedido_numero = (
            SELECT p.pedido_numero FROM producao_diaria p WHERE p.id = estoque_movimentacoes.producao_diaria_id
        )
        WHERE producao_diaria_id IS NOT NULL
          AND (pedido_numero IS NULL OR pedido_numero = '')
          AND EXISTS (
              SELECT 1 FROM producao_diaria p WHERE p.id = estoque_movimentacoes.producao_diaria_id
              AND p.pedido_numero IS NOT NULL AND p.pedido_numero != ''
          )
    """)

    # Segundo caso de preenchimento retroativo: movimentações de separação de
    # revenda (não passam por producao_diaria_id) guardavam o número do
    # pedido só no texto do motivo — "Separação pedido X" / "Estorno
    # separação pedido X". SQLite não tem regex embutida, então extrai em
    # Python mesmo (é um laço pequeno, roda uma vez só por movimentação).
    rows_sep = conn.execute("""
        SELECT id, motivo FROM estoque_movimentacoes
        WHERE (pedido_numero IS NULL OR pedido_numero = '')
          AND (motivo LIKE 'Separação pedido %' OR motivo LIKE 'Estorno separação pedido %')
    """).fetchall()
    for row in rows_sep:
        motivo = (row["motivo"] or "").strip()
        numero = motivo.rsplit(" ", 1)[-1].strip() if motivo else ""
        if numero:
            conn.execute("UPDATE estoque_movimentacoes SET pedido_numero=? WHERE id=?", (numero, row["id"]))

    cols_ped = [r[1] for r in conn.execute("PRAGMA table_info(pedidos)").fetchall()]
    if "acrescimo" not in cols_ped:
        conn.execute("ALTER TABLE pedidos ADD COLUMN acrescimo REAL DEFAULT 0")
    if "frete" not in cols_ped:
        conn.execute("ALTER TABLE pedidos ADD COLUMN frete REAL DEFAULT 0")
    if "desconto_global" not in cols_ped:
        conn.execute("ALTER TABLE pedidos ADD COLUMN desconto_global REAL DEFAULT 0")
    for _c, _t in [("transportadora","TEXT"),("nota_fiscal","TEXT"),("rastreio","TEXT"),
                   ("volumes","INTEGER"),("previsao_entrega","TEXT"),("obs_envio","TEXT"),
                   ("data_despacho","TEXT"),("data_entrega","TEXT"),("frete_pago","REAL DEFAULT 0"),
                   ("precisa_pintura","INTEGER DEFAULT 0")]:
        if _c not in cols_ped:
            conn.execute(f"ALTER TABLE pedidos ADD COLUMN {_c} {_t}")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pedidos_parcelas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pedido_id INTEGER NOT NULL,
            forma_pagamento TEXT,
            vencimento TEXT,
            valor REAL DEFAULT 0,
            FOREIGN KEY (pedido_id) REFERENCES pedidos(id)
        )
    """)

    colaboradores_sql = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='colaboradores'").fetchone()
    if colaboradores_sql and "CHECK(tipo IN" in (colaboradores_sql[0] or ""):
        # A recriação precisa ocorrer fora de transação e com legacy_alter_table ligado,
        # para as FKs das tabelas de produção/EPIs continuarem apontando para colaboradores.
        conn.commit()
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("PRAGMA legacy_alter_table=ON")
        conn.execute("ALTER TABLE colaboradores RENAME TO colaboradores_old")
        conn.execute("""
            CREATE TABLE colaboradores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                tipo TEXT NOT NULL,
                maquina_id INTEGER,
                ativo INTEGER DEFAULT 1,
                criado_em TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (maquina_id) REFERENCES maquinas(id)
            )
        """)
        conn.execute("""
            INSERT INTO colaboradores (id, nome, tipo, maquina_id, ativo, criado_em)
            SELECT id, nome, tipo, maquina_id, ativo, criado_em FROM colaboradores_old
        """)
        conn.execute("DROP TABLE colaboradores_old")
        conn.execute("PRAGMA legacy_alter_table=OFF")
        conn.execute("PRAGMA foreign_keys=ON")

    cols = [row[1] for row in conn.execute("PRAGMA table_info(estoque_produtos)").fetchall()]
    if "codigo" not in cols:
        conn.execute("ALTER TABLE estoque_produtos ADD COLUMN codigo TEXT")

    # pedidos_clientes: garante colunas de contato/endereco em bancos antigos
    # (tabela usa CREATE IF NOT EXISTS, entao tabelas antigas nao recebem colunas novas)
    cols_cli = [row[1] for row in conn.execute("PRAGMA table_info(pedidos_clientes)").fetchall()]
    for _col in ("cnpj", "nome_fantasia", "ie", "email", "telefone",
                 "cep", "logradouro", "numero", "complemento",
                 "bairro", "cidade", "uf", "observacoes"):
        if _col not in cols_cli:
            conn.execute(f"ALTER TABLE pedidos_clientes ADD COLUMN {_col} TEXT")

    cols_prod = [row[1] for row in conn.execute("PRAGMA table_info(producao_diaria)").fetchall()]
    if "pedido_numero" not in cols_prod:
        conn.execute("ALTER TABLE producao_diaria ADD COLUMN pedido_numero TEXT")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS producao_diaria_itens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producao_diaria_id INTEGER NOT NULL,
            produto_estoque_id INTEGER,
            quantidade REAL NOT NULL DEFAULT 0,
            perda_quantidade REAL DEFAULT 0,
            sobra_quantidade REAL DEFAULT 0,
            FOREIGN KEY (producao_diaria_id) REFERENCES producao_diaria(id),
            FOREIGN KEY (produto_estoque_id) REFERENCES estoque_produtos(id)
        )
    """)
    # tipo_perda por item: permite saber qual foi o motivo da perda de CADA
    # produto num lançamento multi-produto (antes só existia em
    # estoque_movimentacoes, sem ligação direta com o item/produto do dia).
    cols_pdi = [row[1] for row in conn.execute("PRAGMA table_info(producao_diaria_itens)").fetchall()]
    if "tipo_perda" not in cols_pdi:
        conn.execute("ALTER TABLE producao_diaria_itens ADD COLUMN tipo_perda TEXT")
    # Migração única: lançamentos antigos de produto único (já têm produto vinculado
    # no cabeçalho) ganham a linha de detalhe correspondente, se ainda não existir.
    # Lançamentos multi-produto antigos não têm como recuperar o detalhe por
    # produto (só o total ficou salvo) e ficam de fora dessa migração.
    conn.execute("""
        INSERT INTO producao_diaria_itens (producao_diaria_id, produto_estoque_id, quantidade, perda_quantidade, sobra_quantidade)
        SELECT p.id, p.produto_estoque_id, p.producao, p.perda_quantidade, p.sobra_quantidade
        FROM producao_diaria p
        WHERE p.produto_estoque_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM producao_diaria_itens pdi WHERE pdi.producao_diaria_id = p.id)
    """)

    cols_cat = [row[1] for row in conn.execute("PRAGMA table_info(estoque_categorias)").fetchall()]
    if "tipo" not in cols_cat:
        conn.execute("ALTER TABLE estoque_categorias ADD COLUMN tipo TEXT DEFAULT 'producao'")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS feriados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL UNIQUE,
            descricao TEXT,
            criado_em TEXT DEFAULT (datetime('now'))
        )
    """)
    # Gera automaticamente os feriados nacionais do ano atual e do próximo
    # (fixos + móveis calculados a partir da Páscoa), toda vez que o sistema
    # sobe — assim nunca fica desatualizado quando o ano vira. Feriados
    # estaduais/municipais continuam por conta do cadastro manual.
    for _ano in (datetime.now().year, datetime.now().year + 1):
        for _data, _desc in _feriados_nacionais(_ano):
            conn.execute("INSERT OR IGNORE INTO feriados (data, descricao) VALUES (?, ?)", (_data, _desc))

    # Anexos na comunicação (foto/documento por recado)
    cols_com = [row[1] for row in conn.execute("PRAGMA table_info(comunicacao_recados)").fetchall()]
    if "anexo_nome" not in cols_com:
        conn.execute("ALTER TABLE comunicacao_recados ADD COLUMN anexo_nome TEXT")
    if "anexo_tipo" not in cols_com:
        conn.execute("ALTER TABLE comunicacao_recados ADD COLUMN anexo_tipo TEXT")
    if "anexo_arquivo" not in cols_com:
        conn.execute("ALTER TABLE comunicacao_recados ADD COLUMN anexo_arquivo TEXT")
    if "conversa_setor" not in cols_com:
        conn.execute("ALTER TABLE comunicacao_recados ADD COLUMN conversa_setor TEXT")
        # Legado: cada recado vai para a conversa do setor de quem escreveu (menos gestor)
        conn.execute("""UPDATE comunicacao_recados SET conversa_setor = autor_setor
                        WHERE conversa_setor IS NULL AND autor_setor IS NOT NULL
                          AND autor_setor != 'gestor'""")
    if "conversa_usuario_id" not in cols_com:
        conn.execute("ALTER TABLE comunicacao_recados ADD COLUMN conversa_usuario_id INTEGER")
        # Legado: cada recado vai para a conversa do próprio autor (menos gestor)
        conn.execute("""UPDATE comunicacao_recados SET conversa_usuario_id = autor_id
                        WHERE conversa_usuario_id IS NULL AND autor_setor IS NOT NULL
                          AND autor_setor != 'gestor'""")

    # Migração para adicionar campo nota_fiscal em estoque_movimentacoes
    cols_mov = [row[1] for row in conn.execute("PRAGMA table_info(estoque_movimentacoes)").fetchall()]
    if "nota_fiscal" not in cols_mov:
        conn.execute("ALTER TABLE estoque_movimentacoes ADD COLUMN nota_fiscal TEXT")

    # Migração do campo Código/ID:
    # A versão anterior criou um índice UNIQUE apenas em codigo. Isso gerava erro 500
    # ao editar um produto quando existia o mesmo código em produto inativo/excluído.
    # A validação de duplicidade ativa fica no backend, retornando erro amigável 400.
    conn.execute("DROP INDEX IF EXISTS idx_estoque_produtos_codigo")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_estoque_produtos_codigo_lookup ON estoque_produtos(codigo)")

    # Garante que todas as chaves de Dados da Empresa existam em bancos antigos.
    # INSERT OR IGNORE preserva os dados já preenchidos pelo usuário.
    default_configs = [
        ("empresa_nome", "PRATIC", "Nome da empresa"),
        ("empresa_cnpj", "", "CNPJ da empresa"),
        ("empresa_telefone", "", "Telefone da empresa"),
        ("empresa_email", "", "E-mail da empresa"),
        ("empresa_cep", "", "CEP da empresa"),
        ("empresa_logradouro", "", "Logradouro da empresa"),
        ("empresa_numero", "", "Número da empresa"),
        ("empresa_bairro", "", "Bairro da empresa"),
        ("empresa_complemento", "", "Complemento da empresa"),
        ("empresa_cidade", "", "Cidade da empresa"),
        ("empresa_uf", "", "UF da empresa"),
        ("empresa_logo", "", "Logo da empresa em base64"),
        ("perm_gestor", "dashboard,producao,premiacao,pintura,colaboradores,maquinas,pedidos,estoque,epi,saldo-demanda,consumo-medio,gerencial,graficos,relatorios,configuracoes,backup,perm-usuarios,permissoes,empresa,mobile,estoque_mobile", "Permissões do perfil Gestor"),
        ("perm_producao", "dashboard,producao,premiacao,pintura,colaboradores,maquinas,epi,relatorios", "Permissões do perfil Produção"),
        ("perm_comercial", "dashboard,pedidos,relatorios", "Permissões do perfil Comercial"),
        ("perm_estoque", "dashboard,estoque,consumo-medio,relatorios,estoque_mobile", "Permissões do perfil Estoque"),
        ("chat_p2p_permitido", "0", "Permitir chat 1:1 privado entre colaboradores"),
        ("exigir_pedido_producao_perfis", "", "Perfis que são obrigados a informar número do pedido em todo lançamento de Produção Diária (lista separada por vírgula, ex: producao,comercial)"),
    ]
    for chave, valor, descricao in default_configs:
        conn.execute(
            "INSERT OR IGNORE INTO configuracoes (chave, valor, descricao) VALUES (?, ?, ?)",
            (chave, valor, descricao)
        )

    # Migração: adiciona novas páginas às permissões de perfis já existentes no banco.
    # INSERT OR IGNORE acima só cria a linha se ela ainda não existir — em bancos que já
    # tinham perm_gestor/perm_estoque salvos, uma página nova (ex.: consumo-medio) nunca
    # entraria na string sem isso, e sumiria do menu mesmo para o gestor.
    _paginas_novas_por_perfil = {
        "perm_gestor": ["consumo-medio", "gerencial", "pintura"],
        "perm_estoque": ["consumo-medio"],
        "perm_producao": ["pintura"],
    }
    for _chave, _paginas in _paginas_novas_por_perfil.items():
        _row = conn.execute("SELECT valor FROM configuracoes WHERE chave = ?", (_chave,)).fetchone()
        if _row:
            _atuais = [p.strip() for p in (_row["valor"] or "").split(",") if p.strip()]
            _faltando = [p for p in _paginas if p not in _atuais]
            if _faltando:
                conn.execute(
                    "UPDATE configuracoes SET valor = ? WHERE chave = ?",
                    (",".join(_atuais + _faltando), _chave)
                )

    # Tabela de permissões por usuário (separada por causa do UNIQUE constraint)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS usuario_permissoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            modulo TEXT NOT NULL,
            acao TEXT NOT NULL,
            permitido INTEGER DEFAULT 1,
            UNIQUE(usuario_id, modulo, acao)
        )
    """)

    conn.commit()
    conn.close()

def seed_data():
    conn = get_conn()
    c = conn.cursor()

    # Só faz seed se banco estiver vazio
    c.execute("SELECT COUNT(*) FROM maquinas")
    if c.fetchone()[0] > 0:
        conn.close()
        return

    # Máquina
    c.execute("INSERT INTO maquinas (nome, setor, meta_padrao) VALUES (?, ?, ?)",
              ("CNC 30", "Produção", 8000))
    maquina_id = c.lastrowid

    # Colaboradores
    c.execute("INSERT INTO colaboradores (nome, tipo, maquina_id) VALUES (?, ?, ?)",
              ("Hyngrisson", "operador", maquina_id))
    hyn_id = c.lastrowid

    c.execute("INSERT INTO colaboradores (nome, tipo, maquina_id) VALUES (?, ?, ?)",
              ("Talita", "operador", maquina_id))
    tal_id = c.lastrowid

    c.execute("INSERT INTO colaboradores (nome, tipo, maquina_id) VALUES (?, ?, ?)",
              ("Hyngrid", "auxiliar", None))
    c.execute("INSERT INTO colaboradores (nome, tipo, maquina_id) VALUES (?, ?, ?)",
              ("Sofia", "auxiliar", None))

    # Dados de Abril (datas seriais Excel convertidas)
    # 46127 = 2026-04-01, etc.
    abril_dados = [
        # (colaborador_id, data, producao)
        (hyn_id, "2026-04-01", 10000),
        (tal_id, "2026-04-01", 9850),
        (hyn_id, "2026-04-02", 10100),
        (tal_id, "2026-04-02", 7150),
        (hyn_id, "2026-04-03", 11200),
        (tal_id, "2026-04-03", 8000),
        (hyn_id, "2026-04-07", 10000),
        (tal_id, "2026-04-07", 8000),
        (hyn_id, "2026-04-09", 6050),
        (tal_id, "2026-04-09", 8000),
        (hyn_id, "2026-04-10", 8000),
        (tal_id, "2026-04-10", 10000),
        (hyn_id, "2026-04-11", 9500),
        (tal_id, "2026-04-11", 7000),
        (hyn_id, "2026-04-14", 9000),
        (tal_id, "2026-04-14", 8000),
        (hyn_id, "2026-04-15", 9500),
        (tal_id, "2026-04-15", 8500),
        (hyn_id, "2026-04-16", 8250),
        (tal_id, "2026-04-16", 6650),
        (hyn_id, "2026-04-17", 7000),
        (tal_id, "2026-04-17", 7000),
    ]

    for col_id, data, producao in abril_dados:
        meta = 8000
        excedente = (producao - meta) if producao > 0 else 0
        mes = "2026-04"
        c.execute("""INSERT INTO producao_diaria 
                     (colaborador_id, maquina_id, data, mes_referencia, meta, producao, excedente)
                     VALUES (?, ?, ?, ?, ?, ?, ?)""",
                  (col_id, maquina_id, data, mes, meta, producao, excedente))

    # Dados de Maio (Planilha4)
    maio_dados = [
        (hyn_id, "2026-05-05", 6300),
        (tal_id, "2026-05-05", 7250),
        (hyn_id, "2026-05-06", 10000),
        (tal_id, "2026-05-06", 8950),
        (hyn_id, "2026-05-07", 10500),
        (tal_id, "2026-05-07", 8200),
        (hyn_id, "2026-05-08", 12000),
        (tal_id, "2026-05-08", 9400),
        (hyn_id, "2026-05-09", 11600),
        (tal_id, "2026-05-09", 8300),
        (hyn_id, "2026-05-12", 10900),
        (tal_id, "2026-05-12", 8300),
        (hyn_id, "2026-05-13", 7300),
        (tal_id, "2026-05-13", 8700),
        (hyn_id, "2026-05-14", 8000),
        (tal_id, "2026-05-14", 7800),
        (hyn_id, "2026-05-15", 7700),
        (tal_id, "2026-05-15", 8800),
        (hyn_id, "2026-05-16", 8300),
        (tal_id, "2026-05-16", 8000),
        (hyn_id, "2026-05-19", 8000),
        (tal_id, "2026-05-19", 8300),
        (hyn_id, "2026-05-20", 5864),
        (tal_id, "2026-05-20", 9700),
        (hyn_id, "2026-05-21", 7200),
        (tal_id, "2026-05-21", 10700),
        (hyn_id, "2026-05-22", 8800),
        (tal_id, "2026-05-22", 10300),
        (hyn_id, "2026-05-23", 8600),
        (tal_id, "2026-05-23", 7500),
        (hyn_id, "2026-05-26", 10300),
        (tal_id, "2026-05-26", 8700),
        (hyn_id, "2026-05-27", 10400),
        (tal_id, "2026-05-27", 8600),
        (hyn_id, "2026-05-28", 0),
        (tal_id, "2026-05-28", 7800),
        (hyn_id, "2026-05-29", 0),
        (tal_id, "2026-05-29", 7800),
    ]

    for col_id, data, producao in maio_dados:
        meta = 8000
        excedente = (producao - meta) if producao > 0 else 0
        mes = "2026-05"
        c.execute("""INSERT INTO producao_diaria 
                     (colaborador_id, maquina_id, data, mes_referencia, meta, producao, excedente)
                     VALUES (?, ?, ?, ?, ?, ?, ?)""",
                  (col_id, maquina_id, data, mes, meta, producao, excedente))

    # Premiação auxiliares Abril
    c.execute("SELECT id FROM colaboradores WHERE nome = 'Hyngrid'")
    hyngrid_id = c.fetchone()[0]
    c.execute("SELECT id FROM colaboradores WHERE nome = 'Sofia'")
    sofia_id = c.fetchone()[0]

    c.execute("INSERT INTO premiacao_auxiliar (colaborador_id, mes_referencia, posicao, valor_bonus) VALUES (?, ?, ?, ?)",
              (sofia_id, "2026-04", 1, 200))
    c.execute("INSERT INTO premiacao_auxiliar (colaborador_id, mes_referencia, posicao, valor_bonus) VALUES (?, ?, ?, ?)",
              (hyngrid_id, "2026-04", 2, 100))

    # Configurações padrão
    configs = [
        ("meta_padrao", "8000", "Meta diária padrão de produção (peças)"),
        ("empresa_nome", "PRATIC", "Nome da empresa"),
        ("empresa_cnpj", "", "CNPJ da empresa"),
        ("empresa_endereco", "", "Endereço da empresa"),
        ("empresa_cep", "", "CEP da empresa"),
        ("empresa_numero", "", "Número da empresa"),
        ("empresa_logradouro", "", "Logradouro da empresa"),
        ("empresa_bairro", "", "Bairro da empresa"),
        ("empresa_complemento", "", "Complemento da empresa"),
        ("empresa_cidade", "", "Cidade da empresa"),
        ("empresa_uf", "", "UF da empresa"),
        ("empresa_telefone", "", "Telefone da empresa"),
        ("empresa_email", "", "E-mail da empresa"),
        ("empresa_logo", "", "Logo da empresa em base64"),
        ("valor_premio_operador", "300", "Valor do prêmio para operador que bater a média"),
        ("valor_premio_operador_1", "300", "Valor do prêmio para o 1º colocado operador"),
        ("valor_premio_operador_2", "200", "Valor do prêmio para o 2º colocado operador"),
        ("qtd_auxiliares_premiados", "2", "Quantidade de auxiliares premiados por mês"),
        ("bonus_auxiliar_1", "200", "Valor do bônus para o 1º auxiliar destaque"),
        ("bonus_auxiliar_2", "100", "Valor do bônus para o 2º auxiliar destaque"),
        ("bonus_auxiliar_3", "50", "Valor do bônus para o 3º auxiliar destaque"),
    ]
    for chave, valor, descricao in configs:
        c.execute("INSERT OR IGNORE INTO configuracoes (chave, valor, descricao) VALUES (?, ?, ?)",
                  (chave, valor, descricao))

    conn.commit()
    conn.close()
