-- Rename the realm to "Mankrik".
UPDATE `realmlist` SET `name` = 'Mankrik' WHERE `id` = 1;

DELETE FROM `motd` WHERE `realmid` = -1;
INSERT INTO `motd` (`realmid`, `text`) VALUES (-1, 'Welcome to Mankrik.');
