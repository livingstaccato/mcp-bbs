# TW2002 Screen Coverage Audit

This report is generated from a `session.jsonl` log by re-running prompt detection offline.

## Inputs

- Log: `games/tw2002/session.jsonl`
- Rules: `games/tw2002/rules.json`

## Summary

- Read events processed: `200000`
- Non-blank screens: `198759`
- Blank screens: `1241`
- Matched screens: `186221`
- Unmatched unique screen hashes: `1742`
- Prompt IDs seen: `35/196` (17.9%)

## Prompt Coverage (Seen)

| Prompt ID | Reads | Unique Screens |
|---|---:|---:|
| `prompt.yes_no` | `40314` | `2192` |
| `prompt.rankings_menu` | `31881` | `34` |
| `prompt.sector_command` | `24371` | `9656` |
| `prompt.planet_command` | `14371` | `731` |
| `prompt.tw_game_menu` | `13834` | `21` |
| `prompt.pause_simple` | `11029` | `605` |
| `prompt.combat_surrender` | `10750` | `269` |
| `prompt.menu_selection` | `6703` | `68` |
| `prompt.login_name` | `6505` | `45` |
| `prompt.interdict` | `6099` | `149` |
| `prompt.port_haggle` | `6086` | `2291` |
| `prompt.port_menu` | `3601` | `140` |
| `prompt.ship_name` | `2824` | `553` |
| `prompt.character_password` | `2207` | `542` |
| `prompt.ship_trade_in` | `1823` | `180` |
| `prompt.stop_in_sector` | `1398` | `1263` |
| `prompt.name_or_bbs` | `827` | `176` |
| `prompt.stardock_buy` | `352` | `230` |
| `prompt.hardware_menu` | `287` | `32` |
| `tedit.select_game` | `242` | `1` |
| `prompt.known_universe_display` | `231` | `224` |
| `prompt.avoid_sector_add` | `212` | `13` |
| `prompt.combat_attack` | `98` | `85` |
| `prompt.autopilot_engage` | `80` | `53` |
| `prompt.hardware_buy` | `29` | `6` |
| `prompt.computer_menu` | `26` | `2` |
| `prompt.corporate_listings` | `9` | `1` |
| `prompt.navpoint_menu` | `7` | `7` |
| `prompt.any_key` | `5` | `1` |
| `prompt.navpoint_settings` | `5` | `5` |
| `prompt.fedspace` | `5` | `5` |
| `prompt.sector_nebula` | `4` | `4` |
| `prompt.private_game_password` | `3` | `3` |
| `prompt.planet_name` | `2` | `2` |
| `prompt.mine_hit` | `1` | `1` |

## Prompt Coverage (Never Seen In Log)

- `prompt.twgs_begin_adventure`
- `prompt.twgs_ship_selection`
- `prompt.twgs_gender`
- `prompt.twgs_real_name`
- `prompt.create_character`
- `prompt.new_player_name`
- `prompt.login_password`
- `prompt.press_any_key`
- `prompt.pause_space_or_enter`
- `prompt.show_todays_log`
- `prompt.include_timestamp`
- `prompt.use_ansi_graphics`
- `prompt.game_password`
- `prompt.enter_number`
- `prompt.command_generic`
- `prompt.more`
- `prompt.twgs_select_game`
- `prompt.port_quantity`
- `prompt.port_price`
- `prompt.port_action`
- `prompt.warp_sector`
- `prompt.start_over`
- `prompt.name_confirm`
- `prompt.what_is_your_name`
- `tedit.admin_password`
- `tedit.main_menu`
- `tedit.general_editor_one`
- `tedit.general_editor_two`
- `tedit.general_editor_three`
- `tedit.user_editor`
- `tedit.port_editor`
- `tedit.sector_editor`
- `tedit.game_timing`
- `tedit.user_list`
- `tedit.enter_number`
- `tedit.enter_value`
- `tedit.confirm`
- `prompt.combat_target`
- `prompt.combat_result`
- `prompt.ship_destroyed`
- `prompt.restart_character`
- `prompt.port_commodity`
- `prompt.port_buy_sell`
- `prompt.port_accept_offer`
- `prompt.port_transaction_complete`
- `prompt.port_no_goods`
- `prompt.port_insufficient_funds`
- `prompt.bank_menu`
- `prompt.bank_amount`
- `prompt.bank_balance`
- `prompt.planet_land`
- `prompt.planet_menu`
- `prompt.planet_colonists`
- `prompt.planet_fighters`
- `prompt.warp_destination`
- `prompt.warp_confirm`
- `prompt.course_plot`
- `prompt.course_engage`
- `prompt.sector_scan`
- `prompt.density_scan`
- `prompt.message_read`
- `prompt.message_compose`
- `prompt.message_recipient`
- `prompt.stardock_menu`
- `prompt.ship_buy`
- `prompt.ship_select`
- `prompt.corp_menu`
- `prompt.corp_join`
- `prompt.corp_deposit`
- `prompt.alien_encounter`
- `prompt.navhaz_warning`
- `prompt.computer_info`
- `prompt.player_info`
- `prompt.rankings`
- `prompt.help_menu`
- `prompt.deploy_fighters`
- `prompt.deploy_mines`
- `prompt.collect_fighters`
- `prompt.photon_fire`
- `prompt.genesis_deploy`
- `prompt.cloak_engage`
- `prompt.out_of_turns`
- `prompt.session_end`
- `prompt.computer_submenu`
- `prompt.course_plotter`
- `prompt.port_report`
- `prompt.known_universe`
- `prompt.cim_mode`
- `prompt.cim_port_data`
- `prompt.cim_sector_data`
- `prompt.cim_ship_data`
- `prompt.tavern_menu`
- `prompt.tavern_bar`
- `prompt.tavern_food`
- `prompt.grimy_trader`
- `prompt.grimy_topic`
- `prompt.grimy_payment`
- `prompt.tricron_game`
- `prompt.tricron_bet`
- `prompt.eavesdrop`
- `prompt.announcement_post`
- `prompt.underground`
- `prompt.underground_password`
- `prompt.fedpolice`
- `prompt.combat_retreat`
- `prompt.combat_captured`
- `prompt.combat_tow_offer`
- `prompt.combat_victory`
- `prompt.combat_loss`
- `prompt.combat_escape_pod`
- `prompt.weapon_disruptor`
- `prompt.weapon_limpet`
- `prompt.weapon_beacon`
- `prompt.weapon_probe`
- `prompt.weapon_psychic_probe`
- `prompt.weapon_genesis`
- `prompt.weapon_atomic`
- `prompt.ship_catalog`
- `prompt.ship_equipment`
- `prompt.ship_purchase_confirm`
- `prompt.ship_yard_menu`
- `prompt.planet_citadel_menu`
- `prompt.planet_colonist_transport`
- `prompt.planet_build_menu`
- `prompt.planet_treasury`
- `prompt.planet_product_pick`
- `prompt.planet_product_drop`
- `prompt.planet_shields`
- `prompt.ferrengi_encounter`
- `prompt.ferrengi_attack`
- `prompt.sector_blackhole`
- `prompt.sector_asteroid`
- `prompt.tow_ship`
- `prompt.tow_release`
- `prompt.mail_list`
- `prompt.mail_delete`
- `prompt.mail_reply`
- `prompt.rankings_display`
- `prompt.twarp_engage`
- `prompt.twarp_confirm`
- `prompt.help_topic`
- `prompt.help_display`
- `prompt.daily_log_display`
- `prompt.bounty_menu`
- `prompt.bounty_collect`
- `prompt.class0_port`
- `prompt.hardware_emporium`
- `prompt.mcplasma`
- `prompt.cloak_status`
- `prompt.scanner_result`
- `prompt.corp_create`
- `prompt.corp_members`
- `prompt.corp_treasury`
- `prompt.corp_planets`
- `prompt.avoid_sector_remove`
- `prompt.photon_quantity`
- `prompt.fighters_quantity`
- `prompt.mines_quantity`
- `prompt.settings_menu`
- `prompt.settings_toggle`
- `prompt.intersector_warp`

## Top Unmatched Screens

These are the most frequently seen screen hashes that did not match any prompt rule.

### `6058c6f8f38298712a95a8a13caf6cd9407e443fddc65bf29f71b1e8adb1fe0d` (reads: 690)

```text
Civilian Cdxdbb8a3                                                              
Civilian Cdx5382e9                                                              
Civilian Cdx8ad957                                                              
Civilian Cdxa95d8a                                                              
Civilian Cdx6ed4e4                                                              
Civilian Cdxba51ad                                                              
Civilian YCdx6f5334                                                             
Civilian YCdxae0634                                                             
Civilian Cdx00890c                                                              
Civilian Cdx84a2f0                                                              
                                                                                
[Pause]                                                                         
```

### `718fe6a9020d1666f2d4369e83f07cda761151c62f83d3fb87fc4747b059c66a` (reads: 258)

```text
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
```

### `5590526a3cfab8191465ec26caa81dc4f4cbf2dc7d5904d489d7f62a67a3b790` (reads: 144)

```text
                                                                                
                                                                                
Run your own TradeWars game for free!                                           
Download TWGS at http://www.eisonline.com                                       
                                                                                
[Pause]                                                                         
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
```

### `5089aef8b55eafbcb32054235786153bfa27d35c522438ed3630baeff1982e42` (reads: 117)

```text
                                                                                
                                                                                
For TW support, news, downloads, the TW blog and more,                          
visit the EIS website at http://www.eisonline.com                               
                                                                                
[Pause]                                                                         
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
```

### `b68730b30b3fd90cecab967558473769c088b0fcf5aaa90113b56d31ce58d214` (reads: 111)

```text
                                                                                
Command [TL=00:00:00]:[99] (?=Help)? : M                                        
<Move>                                                                          
Warps to Sector(s) :  612 - (806) - (1921)                                      
To which Sector [99] ?                                                          
                                                                                
You are already in that sector!                                                 
                                                                                
Command [TL=00:00:00]:[99] (?=Help)? : M                                        
<Move>                                                                          
Warps to Sector(s) :  612 - (806) - (1921)                                      
To which Sector [99] ?                                                          
```

### `aead495a3dd47734d6e559b6c604f0b087f512df55c5da6b837947251186c2cb` (reads: 109)

```text
     \xb7    \xb7                                        .\u2591 \u2584\u2584\u2584\u2584  .                   
 \xb7            \xb7       \xb7                   \xb7         \u2591\u2592\u2593\u2588\u2593\u2592\u2591      \xb7       \xb7    \xb7 
    \xb7            \xb7            \xb7                     \u2591\u25a0\u2593\u2588\u25a0\u2592\u2591\u25a0          \xb7         
         \xb7                     \xb7             \xb7    \xb7 \u2591\u2592\u2593\u2588\u2593\u2592\u2591        \xb7            
       \xb7      \xb7        \xb7         .\xb7                .\u2591 \u2580\u2580\u2580\u2580  .   \xb7      \xb7.       
 \xb7                                      \xb7     \xb7     \u2591\u2592\u2593\u2588\u2593\u2592\u2591                \xb7    
                   \xb7                                \u2591\u2592\u2588\u2588\u2593\u2588\u2591                     
   \xb7                                               .\u2518\u2551\u2588\u2588\u2593\u2588\u2502\u2514.                   
          \xb7                \xb7                 \xb7       \u2502 \u2502  \u2502       \xb7          \xb7  
                    \xb7                \xb7         \xb7                       \xb7        
                                                                                
                                                                                
```

### `9dc569face8f750d452431b3b2f4661107f9d426157a5eec3d541045e2a6c390` (reads: 108)

```text
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
```

### `6a2d32c897d991e657f1faa345b81f5bfee05a6d7a559e9f9613dbd3b66c34aa` (reads: 106)

```text
                                                                                
                                                                                
Join the discussions and follow TradeWars announcements.                        
Be a fan of TradeWars on Facebook at http://www.facebook.com/tw2002             
                                                                                
[Pause]                                                                         
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
```

### `074ab78c0371a161501687a82483310e83b658474df867fdc83bd03536d6f769` (reads: 101)

```text
                                                                                
                                                                                
The BBS community has lost one of its greatest advocates.                       
Doug Rhea, operator of Gamemaster's Realm and BBSFILES.COM,                     
passed away September of 2021.  Our condolences to Doug's family.               
                                                                                
[Pause]                                                                         
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
```

### `835db83a7cddebeb0b3454f5d8209f577708f44291e42ecef4c2f58853562a36` (reads: 100)

```text
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
```

### `d7113a6d614145e1f5c6a57359457f904793aa884a91328addf9a40a3ca59592` (reads: 97)

```text
    . \u2588\u2584\u2580\u2584\u2588 \u2588  \u2588 \u2588  \u2588 \u2584\u2584\u2584\u2580 \xb7  \xb7  \u2580\u2580\u2580\u2580 \u2580\u2580\u2580\u2580 \u2580\u2580\u2580\u2580 \u2580 \xb7    \xb7 \xb7         \u2590\u2588      \xb7    
   \xb7  \u2580\u2580 \u2580\u2580 \u2580 \xb7\u2580 \u2580  \u2580 \u2580\u2580\u2580    \xb7  \xb7   \xb7  \xb7    \xb7 \xb7           \xb7    \u2552\u2550\u2550\u2550\u2550\u2588\u2588\u2555 \xb7       
  . \xb7   \xb7 \xb7    \xb7 \xb7    . \xb7        . \xb7        \xb7   . \xb7    \u250c\u2584\u2584\u2584\u2584\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2580\u2580\u2580\u2580\u2580\u2584\u2584\u2584\u2584  
  \xb7  \xb7      \xb7 . \xb7    \xb7  \xb7             \u250c\u2584\u2584\u2584\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584 
 . \xb7    \xb7    \xb7  \xb7   . \xb7    \xb7    \u2580\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2584\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2593 
   \xb7.    \xb7  .      \xb7   \xb7  \xb7   \xb7  \u251c\u2500\u2500\u2500\u253c\u2500\u2500\u2500\u253c\u2500\u2500\u2500\u253c\u2500\u2500\u2500\u253c\u2500\u2500\u2500\u253c\u2500\u2500\u2500\u253c\u2500\u2500\u2500\u253c\u2500\u2500\u2500\u253c\u2500\u2500\u2500\u253c\u2500\u2500\u2500\u253c\u2500\u2500\u2500\u253c  
   \xb7   .   \xb7  \xb7         \xb7    \xb7   \u2580\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2593 
    \xb7    \xb7. \xb7     . \xb7     \xb7      \xb7  \xb7   \u2580\u2580\u2580\u2580\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2593 
  \xb7   . \xb7   \xb7    \xb7  \xb7   \xb7   \xb7   \xb7   . \xb7   \xb7    \xb7        \xb7 \u2580\u2580\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2580\u2580\xb7 
   \xb7    \xb7   \xb7   . \xb7    \xb7         \xb7    \xb7  \xb7       .  \xb7 \xb7    \xb7   \u2552\u258c\u2588\u2588\u2588\u2588\u2588\u2588\u2593\u2590\u2555  \xb7   
                                                                                
                                                                                
```

### `416d5f117162b9ee74b49f767bf773ba432a2a679ffc80b6a60b279a0f3a2d2b` (reads: 92)

```text
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
```

### `096e33607ef8b76abfcd1786c32c51b39e01a6bf1c2e606f0c52f1d4ee090cc2` (reads: 92)

```text
    . \u2588\u2584\u2580\u2584\u2588 \u2588  \u2588 \u2588  \u2588 \u2584\u2584\u2584\u2580 \xb7  \xb7     \xb7  \xb7    \xb7 \xb7   \xb7    \xb7 \xb7         \u2590\u2588      \xb7    
   \xb7  \u2580\u2580 \u2580\u2580 \u2580 \xb7\u2580 \u2580  \u2580 \u2580\u2580\u2580    \xb7  \xb7   \xb7  \xb7    \xb7 \xb7           \xb7    \u2552\u2550\u2550\u2550\u2550\u2588\u2588\u2555 \xb7       
  . \xb7   \xb7 \xb7    \xb7 \xb7    . \xb7        . \xb7        \xb7   . \xb7    \u250c\u2584\u2584\u2584\u2584\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2580\u2580\u2580\u2580\u2580\u2584\u2584\u2584\u2584  
  \xb7  \xb7      \xb7 . \xb7    \xb7  \xb7             \u250c\u2584\u2584\u2584\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584 
 . \xb7    \xb7    \xb7  \xb7   . \xb7    \xb7    \u2580\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2584\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2593 
   \xb7.    \xb7  .      \xb7   \xb7  \xb7   \xb7  \u251c\u2500\u2500\u2500\u253c\u2500\u2500\u2500\u253c\u2500\u2500\u2500\u253c\u2500\u2500\u2500\u253c\u2500\u2500\u2500\u253c\u2500\u2500\u2500\u253c\u2500\u2500\u2500\u253c\u2500\u2500\u2500\u253c\u2500\u2500\u2500\u253c\u2500\u2500\u2500\u253c\u2500\u2500\u2500\u253c  
   \xb7   .   \xb7  \xb7         \xb7    \xb7   \u2580\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2593 
    \xb7    \xb7. \xb7     . \xb7     \xb7      \xb7  \xb7   \u2580\u2580\u2580\u2580\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2593 
  \xb7   . \xb7   \xb7    \xb7  \xb7   \xb7   \xb7   \xb7   . \xb7   \xb7    \xb7        \xb7 \u2580\u2580\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2580\u2580\xb7 
   \xb7    \xb7   \xb7   . \xb7    \xb7                                                        
                                                                                
                                                                                
```

### `1f649a4ad4e1ebf16dba3286a5aa4683da86ddcebb8c740f308830a893047fbb` (reads: 92)

```text
                                   \xb7                        \u2590\u2591\u2591\u2592\u2593\u2588\u2592\u2588\u2592\u2588\u2592\u2588\u2588\u2592\u2591\u2592\u2592\u2588\u2591 
                 \u2219                                            \u2590\u2591\u2591\u2592\u2593\u2588\u2588\u2588\u2588\u2588\u2591\u2592\u2592\u2592\u2591\u2591\u2591 
                                                                \u2590\u2591\u2591\u2592\u2592\u2593\u2593\u2593\u2588\u2593\u2592\u2592\u2592\u2591\u2591 
 \xb7     \xb7                                 \xb7\u2219 \u2219                       \u2591\u2591\u2592\u2592\u2592\u2593\u2593\u2593\u2588\u2592\u2591 
\xb7                                         \u2219                             \u2591\u2591\u2591\u2591\u2591\u2592\u2592 
           \xb7       \xb7                \xb7                                           
                   \xb7    \xb7                              \xb7   \xb7                    
                                                                                
                                                                                
 \u2588\u2588\u2588\u2588\u2588\u2588\u2510\u2588\u2588\u2588\u2588\u2588\u2588\u2510  \u2588\u2588\u2588\u2588\u2588\u2510 \u2588\u2588\u2588\u2588\u2588\u2588\u2510 \u2588\u2588\u2588\u2588\u2588\u2588\u2510        \u2588\u2588\u2510  \u2588\u2588\u2510 \u2588\u2588\u2588\u2588\u2588\u2510 \u2588\u2588\u2588\u2588\u2588\u2588\u2510 \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2510 
 \u2514\u2500\u2588\u2588\u250c\u2500\u2518\u2588\u2588\u250c\u2500\u2500\u2588\u2588\u2510\u2588\u2588\u250c\u2500\u2500\u2588\u2588\u2510\u2588\u2588\u250c\u2500\u2500\u2588\u2588\u2510\u2588\u2588\u250c\u2500\u2500\u2500\u2518        \u2588\u2588\u2502  \u2588\u2588\u2502\u2588\u2588\u250c\u2500\u2500\u2588\u2588\u2510\u2588\u2588\u250c\u2500\u2500\u2588\u2588\u2510\u2588\u2588\u2500\u2500\u2500\u2500\u2500\u2518 
   \u2593\u2593\u2502                                                                          
```

### `883f89f5954ed762a36832a94e7499601808265d239d7869dbe03a0017a1b1e3` (reads: 92)

```text
     \xb7    \xb7                                        .\u2591 \u2584\u2584\u2584                       
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
```

### `e98d00092d75be4e78d54fa2cf983e7cc49afbb6a164dc7e385f18fb3f735158` (reads: 87)

```text
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
```

### `04c6c7d52d2ca103fc4c9e8a3e5c2ab9f3ca938bfc86e4ef483011ae5faa2622` (reads: 87)

```text
                           \u2219                     \u258c\u2591\u2592\u2593\u2593\u2588\u2593\u2592\u2592\u2592\u2591\u2592\u2592\u2592\u2592\u2591\u2591\u2591\u2592\u2592\u2592  \u2588\u2593\u2593\u2593\u2593\u2588\u2588 
     \xb7                \xb7            \u2219             \u258c\u2591\u2592\u2593\u2592\u2588\u2588\u2593\u2593\u2593\u2593\u2592\u2592\u2592\u2591\u2591\u2591\u2591\u2592\u2592\u2592\u2592\u2593\u2593\u2593\u2593\u2588\u2588\u2593\u2588 
                 \xb7              \xb7   \xb7             \u258c\u2591\u2592\u2593\u2588\u2588\u2592\u2592\u2593\u2593\u2593\u2592\u2592\u2592\u2592\u2592\u2592\u2592\u2592\u2592\u2592\u2588\u2593\u2593\u2588\u2588\u2588\u2588\u2588 
\xb7       \u2219                                          \u258c\u2591\u2592\u2593\u2588\u2588\u2593\u2588\u2593\u2593\u2593\u2593\u2593\u2592\u2592\u2592\u2592\u2592\u2592\u2593\u2593\u2593\u2593\u2593\u2588\u2588\u2593\u2588 
                                                    \u258c\u2591\u2592\u2593\u2588\u2588\u2588\u2588\u2588\u2593\u2593\u2593\u2593\u2593\u2593\u2593\u2593\u2593\u2588\u2588\u2593\u2591\u2588\u2588\u2593\u2588\u2588 
              \xb7            \xb7                         \u258c\u2591\u2592\u2593\u2588\u2588\u2588\u2588\u2588\u2588\u2592\u2588\u2593\u2593\u2593\u2593\u2593\u2593\u2593\u2593\u2593\u2593\u2588\u2591\u2588\u2588 
                                                      \u2590\u2591\u2592\u2593\u2588\u2588\u2593\u2588\u2588\u2588\u2592\u2593\u2593\u2593\u2593\u2593\u2593\u2593\u2593\u2593\u2593\u2588\u2593\u2588\u2588 
  \xb7        \xb7                              \u2219                                     
                                                                                
                                                                                
                                                                                
                                                                                
```

### `0dca9ee36081506b7cd32c6d9778d8a6e6ec096ab560f9f2046760f279909ac6` (reads: 84)

```text
You're not even IN a Corp!                                                      
                                                                                
Corporate command [TL=00:00:00]:[99] (?=Help)? T                                
                                                                                
Sorry, you're not on a Corp.                                                    
                                                                                
Corporate command [TL=00:00:00]:[99] (?=Help)?                                  
                                                                                
Command [TL=00:00:00]:[99] (?=Help)? : M                                        
<Move>                                                                          
Warps to Sector(s) :  612 - (806) - (1921)                                      
To which Sector [99] ?                                                          
```

### `59f4aec47c15cbcb635fc886a6daaa20c4e69edeb8290a2eb26d9b7a71b6488f` (reads: 82)

```text
                                                                                
                                                                                
This is just a moment in time. We will move through it, past it, and be         
together again on the other side                                                
                                                                                
                                       - Drew Markham (Videon) (1958-2018)      
                                                                                
Rest in peace, Drew.                                                            
                                                                                
[Pause]                                                                         
                                                                                
                                                                                
```

### `d584f6258f8cb17c7c6c917838cc909848575d35a18760b0814db61ea7e57217` (reads: 81)

```text
passed away September of 2021.  Our condolences to Doug's family.               
                                                                                
[Pause]                                                                         
                                                                                
A password is required to enter this game.                                      
                                                                                
Password? ********                                                              
                                                                                
You have been on today.                                                         
Searching for messages received since your last time on:                        
No messages received.                                                           
[Pause]                                                                         
```

### `f438719eb4cc314cffd5fb0120ef06ca2f79fb53637868367a19cde2e0954935` (reads: 81)

```text
Rest in peace, Drew.                                                            
                                                                                
[Pause]                                                                         
                                                                                
A password is required to enter this game.                                      
                                                                                
Password? ********                                                              
                                                                                
You have been on today.                                                         
Searching for messages received since your last time on:                        
No messages received.                                                           
[Pause]                                                                         
```

### `fbdb94518c0475055d61ebe75f7f070871828e5bfbcc56d0804279582134cb2b` (reads: 81)

```text
                                                                                
                                                                                
For a list of active TradeWars game sites,                                      
visit TradeWars Jumpgate at http://jumpgate.classictw.com                       
                                                                                
[Pause]                                                                         
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
                                                                                
```

### `788e853424a265a099d5adcb566de27d54f386d501e5b9ff478a252d9459ebdd` (reads: 78)

```text
                                                                                
                                                                                
 \u2588\u2588\u2588\u2588\u2588\u2588\u2510\u2588\u2588\u2588\u2588\u2588\u2588\u2510  \u2588\u2588\u2588\u2588\u2588\u2510 \u2588\u2588\u2588\u2588\u2588\u2588\u2510 \u2588\u2588\u2588\u2588\u2588\u2588\u2510        \u2588\u2588\u2510  \u2588\u2588\u2510 \u2588\u2588\u2588\u2588\u2588\u2510 \u2588\u2588\u2588\u2588\u2588\u2588\u2510 \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2510 
 \u2514\u2500\u2588\u2588\u250c\u2500\u2518\u2588\u2588\u250c\u2500\u2500\u2588\u2588\u2510\u2588\u2588\u250c\u2500\u2500\u2588\u2588\u2510\u2588\u2588\u250c\u2500\u2500\u2588\u2588\u2510\u2588\u2588\u250c\u2500\u2500\u2500\u2518        \u2588\u2588\u2502  \u2588\u2588\u2502\u2588\u2588\u250c\u2500\u2500\u2588\u2588\u2510\u2588\u2588\u250c\u2500\u2500\u2588\u2588\u2510\u2588\u2588\u2500\u2500\u2500\u2500\u2500\u2518 
   \u2593\u2593\u2502  \u2593\u2593\u2593\u2593\u2593\u2593\u250c\u2518\u2593\u2593\u2593\u2593\u2593\u2593\u2593\u2502\u2593\u2593\u2502\xb7 \u2593\u2593\u2502\u2593\u2593\u2593\u2593\u2510     \xb7    \u2593\u2593\u2502\u2593\u2510\u2593\u2593\u2502\u2593\u2593\u2593\u2593\u2593\u2593\u2593\u2502\u2593\u2593\u2593\u2593\u2593\u2593\u250c\u2518\u2593\u2593\u2593\u2593\u2593\u2593\u2593\u2510 
   \u2592\u2592\u2502  \u2592\u2592\u250c\u2592\u2592\u250c\u2518 \u2592\u2592\u2502  \u2592\u2592\u2502\u2592\u2592\u2502  \u2592\u2592\u2502\u2592\u2592\u250c\u2500\u2518          \u2592\u2592\u2502\u2592\u2502\u2592\u2592\u2502\u2592\u2592\u2502  \u2592\u2592\u2502\u2592\u2592\u250c\u2592\u2592\u250c\u2518 \u2514\u2500\u2500\u2500\u2500\u2592\u2592\u2502 
   \u2591\u2591\u2502  \u2591\u2591\u2502\u2514\u2591\u2591\u2591 \u2591\u2591\u2502\xb7 \u2591\u2591\u2502\u2591\u2591\u2591\u2591\u2591\u2591\u250c\u2518\u2591\u2591\u2591\u2591\u2591\u2591\u2510  \xb7     \u2591\u2591\u2591\u2591\u2591\u2591\u2591\u2502\u2591\u2591\u2502  \u2591\u2591\u2502\u2591\u2591\u2502\u2514\u2591\u2591\u2591 \u2591\u2591\u2591\u2591\u2591\u2591\u2591\u2502 
   \u2514\u2500\u2518  \u2514\u2500\u2518 \u2514\u2500\u2500\u2518\u2514\u2500\u2518  \u2514\u2500\u2518\u2514\u2500\u2500\u2500\u2500\u2500\u2518 \u2514\u2500\u2500\u2500\u2500\u2500\u2518        \u2514\u2500\u2500\u2500\u2500\u2500\u2500\u2518\u2514\u2500\u2518\xb7 \u2514\u2500\u2518\u2514\u2500\u2518 \u2514\u2500\u2500\u2518\u2514\u2500\u2500\u2500\u2500\u2500\u2500\u2518 
                                                                  \xb7             
\xb7                  \xb7   \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2510 \u2588\u2588\u2588\u2588\u2588\u2510  \u2588\u2588\u2588\u2588\u2588\u2510 \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2510       \xb7       \xb7       \xb7 
      \xb7        \xb7       \u2514\u2500\u2500\u2500\u2500\u2588\u2588\u2502\u2588\u2588\u250c\u2500\u2500\u2588\u2588\u2510\u2588\u2588\u250c\u2500\u2500\u2588\u2588\u2510\u2514\u2500\u2500\u2500\u2500\u2588\u2588\u2502            \xb7     \xb7      
                                                                                
```

### `08e6c9b0c2358d735b26ad8ed2c5778af460e2d2cf801650b07e132d8e984e86` (reads: 77)

```text
Warps to Sector(s) :  (1045) - (1583)                                           
                                                                                
Command [TL=00:00:00]:[965] (?=Help)? : M                                       
<Move>                                                                          
Warps to Sector(s) :  (1045) - (1583)                                           
To which Sector [965] ?                                                         
                                                                                
You are already in that sector!                                                 
                                                                                
Command [TL=00:00:00]:[965] (?=Help)? : Q                                       
<Quit>                                                                          
Confirmed? (Y/N)?                                                               
```

### `ed6404a6119a65c30aeea6e2f6bff83e0ec76b1973c612cc643fdcd3bad91371` (reads: 77)

```text
Warps to Sector(s) :  (1045) - (1583)                                           
To which Sector [965] ?                                                         
                                                                                
You are already in that sector!                                                 
                                                                                
Command [TL=00:00:00]:[965] (?=Help)? : Q                                       
<Quit>                                                                          
Confirmed? (Y/N)? No                                                            
                                                                                
Command [TL=00:00:00]:[965] (?=Help)? : Q                                       
<Quit>                                                                          
Confirmed? (Y/N)?                                                               
```

### `ad967cfd2f168ca852f1829fd77e93211c2561d798d00c554fc8e29e2b91e00f` (reads: 77)

```text
                                                                                
Command [TL=00:00:00]:[965] (?=Help)? : Q                                       
<Quit>                                                                          
Confirmed? (Y/N)? No                                                            
                                                                                
Command [TL=00:00:00]:[965] (?=Help)? : Q                                       
<Quit>                                                                          
Confirmed? (Y/N)? No                                                            
                                                                                
Command [TL=00:00:00]:[965] (?=Help)? : Q                                       
<Quit>                                                                          
Confirmed? (Y/N)?                                                               
```

### `524898e4ea730da0a122fef9fa34d9c2b3f8dac9c96f6f5be333446e92e6a661` (reads: 77)

```text
                                                                                
Command [TL=00:00:00]:[965] (?=Help)? : Q                                       
<Quit>                                                                          
Confirmed? (Y/N)? No                                                            
                                                                                
Command [TL=00:00:00]:[965] (?=Help)? : Q                                       
<Quit>                                                                          
Confirmed? (Y/N)? No                                                            
                                                                                
Command [TL=00:00:00]:[965] (?=Help)? : Q                                       
<Quit>                                                                          
Confirmed? (Y/N)?                                                               
```

### `8cd666a33231706c0d423ca4d7293d02046582cf4147e0545e496a8b541e786e` (reads: 77)

```text
                                                                                
Sector  : 263 in uncharted space.                                               
Ports   : New Gelugon, Class 1 (BBS)                                            
Traders : Civilian bot032, w/ 30 ftrs,                                          
           in Bbot032's Ship (Mainstay Ltd Merchant Cruiser)                    
Warps to Sector(s) :  104 - (504) - (895) - (1007)                              
                                                                                
Command [TL=00:00:00]:[263] (?=Help)? :                                         
<Re-Display>                                                                    
                                                                                
Sector  : 263 in uncharted space.                                               
Ports   : New Gelugon, Class 1 (BBS)                                            
```

### `3e80451f8af31b42d296c64b0201c8df44248060172ca87ec105d3325204590a` (reads: 74)

```text
                                                                                
Command [TL=00:00:00]:[1798] (?=Help)? : Q                                      
<Quit>                                                                          
Confirmed? (Y/N)? No                                                            
                                                                                
Command [TL=00:00:00]:[1798] (?=Help)? : Q                                      
<Quit>                                                                          
Confirmed? (Y/N)? No                                                            
                                                                                
Command [TL=00:00:00]:[1798] (?=Help)? : Q                                      
<Quit>                                                                          
Confirmed? (Y/N)?                                                               
```

### `f0bc266bcce907caa5df09c6c731a4534a8b7dce40c900fd13ff60e7edd73936` (reads: 74)

```text
                                                                                
Command [TL=00:00:00]:[1066] (?=Help)? : M                                      
<Move>                                                                          
Warps to Sector(s) :  (290) - 914 - (1700)                                      
To which Sector [1066] ?                                                        
                                                                                
You are already in that sector!                                                 
                                                                                
Command [TL=00:00:00]:[1066] (?=Help)? : M                                      
<Move>                                                                          
Warps to Sector(s) :  (290) - 914 - (1700)                                      
To which Sector [1066] ?                                                        
```

## Next Actions

- Add/adjust rules in `games/tw2002/rules.json` for the top unmatched hashes above.
- If a screen is a data display (not an input prompt), add `expect_cursor_at_end: false` patterns or exclude it explicitly.
- Rerun this audit after changes to confirm coverage improved.

