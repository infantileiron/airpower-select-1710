
/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!50503 SET NAMES utf8mb4 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
DROP TABLE IF EXISTS `settlement_hours`;
CREATE TABLE `settlement_hours` (
  `id` int NOT NULL AUTO_INCREMENT,
  `settlement_id` int NOT NULL,
  `hour` varchar(30) NOT NULL,
  `baseline_kwh` float DEFAULT NULL,
  `actual_kwh` float DEFAULT NULL,
  `saved_kwh` float DEFAULT NULL,
  `price` float DEFAULT NULL,
  `amount` float DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_settlement_hour` (`settlement_id`,`hour`),
  CONSTRAINT `settlement_hours_ibfk_1` FOREIGN KEY (`settlement_id`) REFERENCES `settlements` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
DROP TABLE IF EXISTS `settlements`;
CREATE TABLE `settlements` (
  `id` int NOT NULL AUTO_INCREMENT,
  `pilot_id` int NOT NULL,
  `state` varchar(20) DEFAULT 'failed',
  `total_kwh` float DEFAULT 0,
  `total_amount` float DEFAULT 0,
  `basis_checksum` varchar(80) DEFAULT '',
  `gaps` json DEFAULT NULL,
  `created` varchar(40) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `pilot_id` (`pilot_id`),
  CONSTRAINT `settlements_ibfk_1` FOREIGN KEY (`pilot_id`) REFERENCES `pilots` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
DROP TABLE IF EXISTS `pilots`;
CREATE TABLE `pilots` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) DEFAULT NULL,
  `run_id` int DEFAULT NULL,
  `start_hour` varchar(30) NOT NULL,
  `end_hour` varchar(30) NOT NULL,
  `status` varchar(20) DEFAULT 'open',
  `settlement_id` int DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `run_id` (`run_id`),
  KEY `settlement_id` (`settlement_id`),
  CONSTRAINT `pilots_ibfk_1` FOREIGN KEY (`run_id`) REFERENCES `runs` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
DROP TABLE IF EXISTS `tariffs`;
CREATE TABLE `tariffs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) DEFAULT NULL,
  `start_hour` varchar(30) NOT NULL,
  `end_hour` varchar(30) NOT NULL,
  `price` float NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
